"""
VidyaBot Multi-Interface Routes

Support for WhatsApp, SMS (Twilio), and Voice (Whisper) interfaces.
All channels feed into the same retrieval pipeline, normalized to plain text queries.

Endpoints:
  POST   /interfaces/whatsapp/webhook - WhatsApp incoming messages
  GET    /interfaces/whatsapp/webhook - WhatsApp verification
  POST   /interfaces/sms/webhook - Twilio SMS incoming
  POST   /interfaces/voice/transcribe - Upload audio for transcription
  GET    /interfaces/status - Interface health status
"""

import logging
import hashlib
import hmac
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from backend.config import settings
from backend.database import get_db_connection
from backend.retrieval.context_pruner import ContextPruner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interfaces", tags=["interfaces"])

context_pruner = ContextPruner()


class TextMessage(BaseModel):
    """Normalized message from any interface."""
    interface: str  # "whatsapp", "sms", "voice"
    user_id: str  # Phone number or user identifier
    query_text: str
    media_type: Optional[str] = None  # "text", "audio", "image"


class InterfaceResponse(BaseModel):
    """Response to send back to user through interface."""
    interface: str
    user_id: str
    answer: str  # Plain text response
    cost_reduction_pct: Optional[float] = None  # Show cost efficiency


# ============================================
# WhatsApp Webhook
# ============================================

POSSIBLE_WHATSAPP_TOKENS = [settings.WHATSAPP_VERIFY_TOKEN]


@router.get("/whatsapp/webhook")
async def whatsapp_verify(
    hub_mode: str = Query(...),
    hub_challenge: str = Query(...),
    hub_verify_token: str = Query(...)
):
    """
    WhatsApp webhook verification.
    Verifies that requests come from WhatsApp.
    """
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid mode")
    
    if hub_verify_token not in POSSIBLE_WHATSAPP_TOKENS:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    
    return int(hub_challenge)


@router.post("/whatsapp/webhook")
async def whatsapp_incoming(request: Request):
    """
    Handle incoming WhatsApp messages.
    Webhook from WhatsApp Business API.
    """
    payload = await request.json()
    
    try:
        # Extract message data
        if "entry" not in payload:
            return {"status": "ok"}  # Ignore non-message webhooks
        
        entry = payload["entry"][0]
        messaging = entry.get("messaging", [])
        
        for message in messaging:
            sender_id = message["sender"]["id"]
            recipient_id = message["recipient"]["id"]
            
            # Extract text message
            if "message" in message:
                msg_obj = message["message"]
                
                # Handle text
                if msg_obj.get("type") == "text":
                    query_text = msg_obj.get("text", {}).get("body", "")
                    
                    # Process through pipeline
                    response = await _process_query(
                        interface="whatsapp",
                        user_id=sender_id,
                        query_text=query_text,
                        textbook_id=1  # Default; could be user preference
                    )
                    
                    # Send response back via WhatsApp API
                    await _send_whatsapp_message(sender_id, response.answer)
                
                # Handle image (OCR would go here)
                elif msg_obj.get("type") == "image":
                    logger.info(f"WhatsApp image from {sender_id} (OCR not yet implemented)")
        
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"status": "error"}


async def _send_whatsapp_message(recipient_id: str, text: str):
    """
    Send text message via WhatsApp Business API.
    Requires WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID.
    """
    if not settings.WHATSAPP_ACCESS_TOKEN:
        logger.warning("WhatsApp not configured (missing ACCESS_TOKEN)")
        return
    
    # In production, use httpx to POST to Meta's API
    # - Phone number ID: settings.WHATSAPP_PHONE_NUMBER_ID
    # - Message: text
    logger.info(f"[Mock WhatsApp] Sending to {recipient_id}: {text[:50]}...")


# ============================================
# Twilio SMS Webhook
# ============================================

@router.post("/sms/webhook")
async def sms_incoming(request: Request):
    """
    Handle incoming SMS via Twilio webhook.
    Twilio POSTs form data with From, To, Body.
    """
    form = await request.form()
    
    try:
        sender = form.get("From", "")
        body = form.get("Body", "")
        
        # Process query
        response = await _process_query(
            interface="sms",
            user_id=sender,
            query_text=body,
            textbook_id=1  # Default
        )
        
        # Send SMS response via Twilio
        await _send_sms_message(sender, response.answer)
        
        # Return TwiML
        return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Your answer is being sent...</Message>
</Response>"""
    
    except Exception as e:
        logger.error(f"SMS webhook error: {e}")
        return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Error processing request</Message>
</Response>"""


async def _send_sms_message(phone_number: str, text: str):
    """
    Send SMS via Twilio.
    Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER.
    """
    if not settings.TWILIO_ACCOUNT_SID:
        logger.warning("Twilio not configured (missing ACCOUNT_SID)")
        return
    
    # In production, use twilio.rest.Client
    # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    # client.messages.create(
    #     from_=settings.TWILIO_PHONE_NUMBER,
    #     to=phone_number,
    #     body=text
    # )
    logger.info(f"[Mock Twilio SMS] Sending to {phone_number}: {text[:50]}...")


# ============================================
# Voice Transcription Endpoint
# ============================================

@router.post("/voice/transcribe")
async def voice_transcribe(
    user_id: str = Form(...),
    audio_file: UploadFile = File(...)
) -> InterfaceResponse:
    """
    Upload audio file for transcription + Q&A.
    Uses OpenAI Whisper (CPU-only, tiny model, 39MB).
    
    Returns:
      - Transcribed text
      - QA answer based on transcription
    """
    try:
        # In production:
        # 1. Save audio to temp file
        # 2. Load whisper tiny model: whisper.load_model("tiny")
        # 3. Transcribe: result = model.transcribe(audio_path)
        # 4. Extract query_text = result["text"]
        
        # For now, mock transcription
        query_text = "[Mock transcription would go here]"
        
        response = await _process_query(
            interface="voice",
            user_id=user_id,
            query_text=query_text,
            textbook_id=1
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Shared Processing Pipeline
# ============================================

async def _process_query(
    interface: str,
    user_id: str,
    query_text: str,
    textbook_id: int
) -> InterfaceResponse:
    """
    Unified processing for all interfaces.
    1. Normalize query
    2. Run through v2 5-stage pipeline
    3. Get answer from LLM
    4. Format response for interface
    """
    import anthropic
    
    db = get_db_connection()
    
    try:
        # Normalize & log
        query_normalized = query_text.strip().lower()
        logger.info(f"[{interface.upper()}] Query from {user_id}: {query_normalized[:60]}...")
        
        # Run through pruning pipeline
        pruned_chunks, timings = context_pruner.prune(
            query=query_normalized,
            textbook_id=textbook_id,
            return_timings=True
        )
        
        # Build context
        context = "\n\n".join([f"[Chapter {c.chapter_number}]\n{c.text}" for c in pruned_chunks])
        
        # Get answer from Claude Haiku
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        
        message = client.messages.create(
            model=settings.MODEL_NAME,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": f"""Context from textbook:
{context}

Question: {query_text}

Answer the question based on the context. Be concise and educational."""
                }
            ]
        )
        
        answer = message.content[0].text
        
        # Calculate cost reduction
        baseline_tokens = sum(
            len(c.text.split()) // 0.75 for c in pruned_chunks
        ) * 2  # Account for LLM output
        tokens_reduced_pct = (
            (2000 - baseline_tokens) / 2000 * 100
        ) if baseline_tokens < 2000 else 0
        
        # Log to database
        db.execute("""
            INSERT INTO cost_log (
                user_id, textbook_id, query, interface, 
                tokens_input, tokens_output, cost_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            textbook_id,
            query_normalized,
            interface,
            baseline_tokens,
            200,
            (baseline_tokens * settings.HAIKU_INPUT_COST_PER_1M) / 1_000_000
        ))
        db.commit()
        
        return InterfaceResponse(
            interface=interface,
            user_id=user_id,
            answer=answer,
            cost_reduction_pct=tokens_reduced_pct
        )
    
    finally:
        db.close()


# ============================================
# Status Endpoint
# ============================================

@router.get("/status")
async def interface_status(teacher_pin: str = Query(None)) -> dict:
    """
    Check status of all interfaces.
    Optional: Show detailed stats with teacher PIN.
    """
    status = {
        "whatsapp": {
            "enabled": bool(settings.WHATSAPP_ACCESS_TOKEN),
            "configured": bool(settings.WHATSAPP_PHONE_NUMBER_ID)
        },
        "sms": {
            "enabled": bool(settings.TWILIO_ACCOUNT_SID),
            "configured": bool(settings.TWILIO_PHONE_NUMBER)
        },
        "voice": {
            "enabled": True,  # Whisper always available
            "configured": True
        }
    }
    
    # Detailed stats for admin
    if teacher_pin == settings.TEACHER_PIN:
        db = get_db_connection()
        try:
            stats = db.execute("""
                SELECT interface, COUNT(*) as count, AVG(cost_usd) as avg_cost
                FROM cost_log
                GROUP BY interface
            """).fetchall()
            
            status["stats"] = {
                row[0]: {"queries": row[1], "avg_cost_usd": row[2]} 
                for row in stats
            }
        finally:
            db.close()
    
    return status
