"""
modal_finetune.py — VidyaBot Modal Fine-Tuning Job

Trains Mistral 7B Instruct on student Q&A data using LoRA (PEFT).
Saves merged model weights to a Modal Volume for local download.

Usage (from project root, after `modal token new`):
    modal run modal_finetune.py

Prerequisites:
    pip install modal
    modal token new
    # Claim credits: https://modal.com/account/billing → code: 8WD-WJE-SJQ
"""

import modal
import json
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Modal infrastructure setup
# ──────────────────────────────────────────────────────────────

# Persistent volume to store model output across container restarts
volume = modal.Volume.from_name("vidyabot-model-output", create_if_missing=True)
MODEL_OUTPUT_DIR = "/model-output"

# Container image with all ML dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers>=4.40.0",
        "torch>=2.2.0",
        "peft>=0.10.0",
        "datasets>=2.18.0",
        "bitsandbytes>=0.43.0",
        "huggingface-hub>=0.22.0",
        "accelerate>=0.29.0",
        "scipy",
        "sentencepiece",
        "protobuf",
    )
    .add_local_file(
        "data/finetuning/student_qa.jsonl",
        remote_path="/data/student_qa.jsonl",
    )
)

app = modal.App("vidyabot-finetune", image=image)


# ──────────────────────────────────────────────────────────────
# Fine-tuning function
# ──────────────────────────────────────────────────────────────

@app.function(
    gpu="A10G",          # A10G: 24GB VRAM, ~$1.10/hr — cheaper than A100 and enough for 7B
    timeout=3600 * 3,    # 3 hours max
    volumes={MODEL_OUTPUT_DIR: volume},
)
def finetune_mistral():
    """
    Fine-tune Mistral 7B Instruct on student Q&A data using LoRA.
    
    Pipeline:
    1. Load student_qa.jsonl from mounted local file
    2. Format as Mistral [INST] chat template
    3. Tokenize with padding/truncation
    4. Load Mistral-7B-Instruct-v0.1 in 4-bit (QLoRA)
    5. Apply LoRA adapters (r=8, target: q_proj, v_proj)
    6. Train 3 epochs with DataCollatorForLanguageModeling
    7. Merge LoRA into base model (full weights)
    8. Save merged model to Modal Volume
    """

    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
        DataCollatorForLanguageModeling,
        BitsAndBytesConfig,
    )
    from datasets import Dataset
    from peft import (
        LoraConfig,
        get_peft_model,
        TaskType,
        prepare_model_for_kbit_training,
    )

    print("=" * 60)
    print("  VidyaBot Mistral 7B Fine-Tuning — Modal A10G GPU")
    print("=" * 60)

    # ── Step 1: Load & format dataset ─────────────────────────
    print("\n[1/7] Loading dataset from /data/student_qa.jsonl...")
    qa_data = []
    with open("/data/student_qa.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    qa_data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"  ⚠️  Skipping malformed line: {e}")

    print(f"  ✅ Loaded {len(qa_data)} Q&A pairs")

    if len(qa_data) < 10:
        raise ValueError(f"Dataset too small ({len(qa_data)} examples). Run generate_synthetic_qa.py first.")

    # Format as Mistral instruct template
    def format_instruct(example: dict) -> str:
        """Format using Mistral's [INST] chat template."""
        context = example.get("context", "")
        context_note = f"\n\nContext: {context}" if context else ""
        return (
            f"<s>[INST] You are VidyaBot, an expert tutor for Indian school students "
            f"studying NCERT curriculum. Give a clear, structured answer in 2-4 sentences.{context_note}\n\n"
            f"{example['question']} [/INST] "
            f"{example['answer']} </s>"
        )

    texts = [format_instruct(qa) for qa in qa_data]
    dataset = Dataset.from_dict({"text": texts})
    print(f"  ✅ Dataset formatted ({len(dataset)} examples)")

    # ── Step 2: Load tokenizer ────────────────────────────────
    print("\n[2/7] Loading tokenizer...")
    model_name = "mistralai/Mistral-7B-Instruct-v0.1"

    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    tokenizer.pad_token = tokenizer.eos_token  # Required for batched training
    tokenizer.padding_side = "right"           # Mistral: pad on right

    # ── Step 3: Tokenize dataset ──────────────────────────────
    print("\n[3/7] Tokenizing dataset...")

    def tokenize(examples):
        tokens = tokenizer(
            examples["text"],
            truncation=True,
            max_length=512,
            padding=False,  # DataCollator handles dynamic padding
        )
        tokens["labels"] = tokens["input_ids"].copy()
        return tokens

    tokenized_dataset = dataset.map(
        tokenize,
        batched=True,
        remove_columns=["text"],
    )
    print(f"  ✅ Tokenized {len(tokenized_dataset)} examples")

    # ── Step 4: Load model in 4-bit (QLoRA) ──────────────────
    print("\n[4/7] Loading Mistral-7B-Instruct-v0.1 in 4-bit (QLoRA)...")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
    )
    model = prepare_model_for_kbit_training(model)
    print("  ✅ Model loaded in 4-bit")

    # ── Step 5: Apply LoRA adapters ───────────────────────────
    print("\n[5/7] Configuring LoRA adapters...")

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── Step 6: Train ─────────────────────────────────────────
    print("\n[6/7] Starting LoRA fine-tuning...")

    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,  # Causal LM, not masked
    )

    training_args = TrainingArguments(
        output_dir="/tmp/lora-checkpoints",
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,   # Effective batch = 8
        learning_rate=2e-4,
        warmup_ratio=0.05,
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        fp16=True,
        logging_steps=5,
        save_strategy="epoch",
        save_total_limit=1,
        report_to="none",               # No wandb
        dataloader_pin_memory=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )

    train_result = trainer.train()
    print(f"\n  ✅ Training complete!")
    print(f"     Loss: {train_result.training_loss:.4f}")
    print(f"     Runtime: {train_result.metrics.get('train_runtime', 0):.0f}s")

    # ── Step 7: Merge LoRA into base model + save ─────────────
    print(f"\n[7/7] Merging LoRA weights and saving to {MODEL_OUTPUT_DIR}...")

    # Merge LoRA into base model for full weights (needed for GGUF conversion)
    merged_model = model.merge_and_unload()

    output_path = f"{MODEL_OUTPUT_DIR}/mistral-vidyabot-merged"
    merged_model.save_pretrained(output_path, safe_serialization=True)
    tokenizer.save_pretrained(output_path)

    # Commit to Modal Volume
    volume.commit()

    print(f"\n  ✅ Merged model saved to: {output_path}")
    print("  📦 Model committed to Modal Volume 'vidyabot-model-output'")
    print("\n" + "=" * 60)
    print("  FINE-TUNING COMPLETE")
    print("  Next: run `modal volume get vidyabot-model-output mistral-vidyabot-merged .`")
    print("=" * 60)

    return output_path


# ──────────────────────────────────────────────────────────────
# Local entrypoint
# ──────────────────────────────────────────────────────────────

@app.local_entrypoint()
def main():
    """Submit fine-tuning job to Modal and wait for completion."""
    import os

    # Verify dataset exists before submitting
    dataset_file = "data/finetuning/student_qa.jsonl"
    if not os.path.exists(dataset_file):
        print(f"❌ Dataset not found: {dataset_file}")
        print("   Run: python data/finetuning/generate_synthetic_qa.py")
        return

    # Count examples
    with open(dataset_file, encoding="utf-8") as f:
        count = sum(1 for line in f if line.strip())

    if count < 20:
        print(f"⚠️  Only {count} examples in dataset. Recommend 50+.")
        print("   Run: python data/finetuning/generate_synthetic_qa.py")
        response = input("Continue anyway? [y/N]: ").strip().lower()
        if response != "y":
            return

    print(f"✅ Dataset found: {count} Q&A pairs")
    print(f"🚀 Submitting fine-tuning job to Modal A10G GPU...")
    print(f"   Estimated time: 1-3 hours")
    print(f"   Estimated cost: ~$3-5 (from $250 credits)")
    print()

    result = finetune_mistral.remote()
    print(f"\n✅ Job complete! Weights saved to Modal Volume.")
    print(f"   Path: {result}")
    print()
    print("📥 To download the merged model, run:")
    print("   modal volume get vidyabot-model-output mistral-vidyabot-merged ./backend/llm/models/")
    print()
    print("🔧 Then convert to GGUF and load into Ollama:")
    print("   python modal_convert_gguf.py")
