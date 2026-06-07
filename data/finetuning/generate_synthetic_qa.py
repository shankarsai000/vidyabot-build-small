"""
generate_synthetic_qa.py

Expand the seed student_qa.jsonl to 60+ examples using the local Ollama client.
Runs completely offline — no cloud needed.

Usage (from project root):
    python data/finetuning/generate_synthetic_qa.py

Requirements:
    - Ollama running: ollama serve
    - Model pulled:  ollama pull mistral:latest
"""

import json
import sys
import os
import re

# Add project root to path so we can import the backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.llm.ollama_client import OllamaClient
from backend.config import settings

SEED_FILE = os.path.join(os.path.dirname(__file__), "student_qa.jsonl")
OUTPUT_FILE = SEED_FILE  # We append to the same file

# ──────────────────────────────────────────────
# Topics for synthetic Q&A generation
# Each tuple: (topic, chapter_reference, subject)
# ──────────────────────────────────────────────
TOPICS = [
    # Biology
    ("Photosynthesis — light vs dark reactions", "Biology Class 10, Chapter 5: Life Processes", "biology"),
    ("Cellular respiration — aerobic vs anaerobic", "Biology Class 10, Chapter 5: Life Processes", "biology"),
    ("Structure of a plant cell", "Biology Class 10, Chapter 1: Cell Structure", "biology"),
    ("Human digestive system", "Biology Class 10, Chapter 6: Life Processes", "biology"),
    ("Excretion in humans — kidneys", "Biology Class 10, Chapter 6: Life Processes", "biology"),
    ("Reflex arc in the nervous system", "Biology Class 10, Chapter 7: Control and Coordination", "biology"),
    ("Plant hormones — auxin and gibberellin", "Biology Class 10, Chapter 7: Control and Coordination", "biology"),
    ("Reproduction in plants — pollination", "Biology Class 10, Chapter 8: How do Organisms Reproduce?", "biology"),
    ("Mendel's laws of inheritance", "Biology Class 10, Chapter 9: Heredity and Evolution", "biology"),
    ("Food chain and ecosystem", "Biology Class 10, Chapter 15: Our Environment", "biology"),
    # Physics
    ("Ohm's Law and electrical resistance", "Physics Class 10, Chapter 12: Electricity", "physics"),
    ("Magnetic field and electromagnets", "Physics Class 10, Chapter 13: Magnetic Effects of Electric Current", "physics"),
    ("Reflection of light — laws and mirror formula", "Physics Class 10, Chapter 10: Light – Reflection and Refraction", "physics"),
    ("Refraction of light — Snell's law", "Physics Class 10, Chapter 10: Light – Reflection and Refraction", "physics"),
    ("The human eye — near and far sightedness", "Physics Class 10, Chapter 11: The Human Eye and the Colourful World", "physics"),
    ("Sources of energy — renewable vs non-renewable", "Physics Class 10, Chapter 14: Sources of Energy", "physics"),
    ("Work, Power, and Energy", "Physics Class 10, Chapter 11: Work and Energy", "physics"),
    ("Gravitational force and free fall", "Physics Class 10, Chapter 10: Gravitation", "physics"),
    # Chemistry
    ("Types of chemical reactions", "Chemistry Class 10, Chapter 1: Chemical Reactions and Equations", "chemistry"),
    ("Corrosion and rusting prevention", "Chemistry Class 10, Chapter 1: Chemical Reactions and Equations", "chemistry"),
    ("Properties of metals and non-metals", "Chemistry Class 10, Chapter 3: Metals and Non-metals", "chemistry"),
    ("Carbon compounds — hydrocarbons", "Chemistry Class 10, Chapter 4: Carbon and its Compounds", "chemistry"),
    ("Soaps and detergents — how they work", "Chemistry Class 10, Chapter 4: Carbon and its Compounds", "chemistry"),
    ("Electrolysis and electroplating", "Chemistry Class 10, Chapter 3: Metals and Non-metals", "chemistry"),
    # Mathematics
    ("Arithmetic progressions — nth term", "Mathematics Class 10, Chapter 5: Arithmetic Progressions", "math"),
    ("Similar triangles and Pythagoras theorem", "Mathematics Class 10, Chapter 6: Triangles", "math"),
    ("Surface area and volume of cylinders", "Mathematics Class 10, Chapter 13: Surface Areas and Volumes", "math"),
    ("Probability — basic concepts", "Mathematics Class 10, Chapter 15: Probability", "math"),
    ("Linear equations in two variables", "Mathematics Class 10, Chapter 3: Pair of Linear Equations", "math"),
    # Hindi-language questions (bilingual)
    ("प्रकाश का परावर्तन", "भौतिकी कक्षा 10, अध्याय 10: प्रकाश", "physics_hindi"),
    ("रासायनिक अभिक्रिया के प्रकार", "रसायन विज्ञान कक्षा 10, अध्याय 1", "chemistry_hindi"),
    ("मानव पाचन तंत्र", "जीव विज्ञान कक्षा 10, अध्याय 6", "biology_hindi"),
]

SYSTEM_PROMPT = """You are an educational content generator for Indian school students.
Your task: Generate a realistic, curriculum-aligned question-answer pair for NCERT Class 10 students.
Rules:
- Question must be clear and exam-appropriate
- Answer must be 2-4 sentences, precise and factual
- Use the exact NCERT terminology
- Output ONLY in this exact format (no extra text):
Q: <question here>
A: <answer here>"""

def make_user_prompt(topic: str, chapter: str, subject: str) -> str:
    lang_note = " Answer in Hindi." if subject.endswith("_hindi") else ""
    return f"Topic: {topic}\nChapter reference: {chapter}\n\nGenerate one question-answer pair about this topic for a Class 10 student.{lang_note}"


def parse_qa(raw: str) -> tuple[str, str] | None:
    """Extract Q and A from the LLM's formatted response."""
    # Try standard Q:/A: format
    q_match = re.search(r"Q:\s*(.+?)(?=\nA:|$)", raw, re.DOTALL)
    a_match = re.search(r"A:\s*(.+)", raw, re.DOTALL)
    if q_match and a_match:
        q = q_match.group(1).strip()
        a = a_match.group(1).strip()
        # Remove any trailing "Q:" that spilled over
        a = re.split(r"\nQ:", a)[0].strip()
        return q, a
    return None


def load_existing(filepath: str) -> set:
    """Load existing questions to avoid duplicates."""
    seen = set()
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                        seen.add(obj.get("question", "").lower().strip())
                    except json.JSONDecodeError:
                        pass
    return seen


def main():
    print("=" * 60)
    print("  VidyaBot Synthetic Q&A Generator")
    print("=" * 60)

    # Check Ollama is available
    client = OllamaClient(model="mistral:latest", timeout=90)
    if not client.validate_connection():
        print("\n❌ ERROR: Ollama is not running.")
        print("   Start it with:  ollama serve")
        print("   Pull the model: ollama pull mistral:latest")
        sys.exit(1)

    print(f"\n✅ Ollama connected (model: mistral:latest)")

    # Load existing data to avoid duplicates
    existing_questions = load_existing(SEED_FILE)
    print(f"📂 Existing Q&A pairs: {len(existing_questions)}")
    print(f"🎯 Target: 60+ total pairs")
    print(f"📝 Generating {len(TOPICS)} synthetic pairs...\n")

    generated = []
    failed = 0

    for i, (topic, chapter, subject) in enumerate(TOPICS, 1):
        user_prompt = make_user_prompt(topic, chapter, subject)

        try:
            response = client.ask(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=250
            )
            raw_text = response.answer.strip()

            parsed = parse_qa(raw_text)
            if not parsed:
                print(f"  [{i:02d}] ⚠️  Could not parse response for '{topic}' — skipping")
                failed += 1
                continue

            question, answer = parsed

            # Skip duplicates
            if question.lower().strip() in existing_questions:
                print(f"  [{i:02d}] ⏭️  Duplicate skipped: '{question[:50]}...'")
                continue

            pair = {
                "question": question,
                "answer": answer,
                "context": chapter + " (synthetic)"
            }
            generated.append(pair)
            existing_questions.add(question.lower().strip())
            print(f"  [{i:02d}] ✅ {question[:65]}")

        except Exception as e:
            print(f"  [{i:02d}] ❌ Error on '{topic}': {e}")
            failed += 1

    # Append to file
    if generated:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            for pair in generated:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # Summary
    print("\n" + "=" * 60)
    total = len(existing_questions)
    print(f"✅ Generated: {len(generated)} new pairs")
    print(f"❌ Failed:    {failed}")
    print(f"📊 Total in dataset: {total}")
    print(f"📁 File: {OUTPUT_FILE}")

    if total >= 50:
        print("\n🎉 Dataset is ready for Modal fine-tuning! (50+ pairs)")
    else:
        print(f"\n⚠️  Only {total} pairs. Run again or add more TOPICS to reach 50+.")


if __name__ == "__main__":
    main()
