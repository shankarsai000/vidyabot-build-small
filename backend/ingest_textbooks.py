import os
import sys
import requests
import sqlite3
import numpy as np
from pathlib import Path

# Enforce UTF-8 encoding on standard streams to prevent Windows console encoding crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import get_db_connection, init_db
from backend.ingestion.pdf_parser import PDFParser
from backend.ingestion.chunker import Chunker
from backend.ingestion.embedder import Embedder
from backend.retrieval.context_pruner import ContextPruner
from backend.config import settings

# Try importing fitz for PDF generation fallback
try:
    import fitz
except ImportError:
    fitz = None

TEXTBOOKS_DIR = Path("data/textbooks")

TEXTBOOKS_INFO = [
    {
        "filename": "Biology_Class10_Ch5.pdf",
        "url": "https://ncert.nic.in/textbook/pdf/kesy101.pdf",
        "title": "Biology Class 10 - Photosynthesis & Respiration",
        "board": "CBSE",
        "subject": "Biology",
        "grade": "10",
        "content": {
            "Chapter 5 Life Processes": {
                "Photosynthesis": [
                    "Photosynthesis is the process by which green plants and some other organisms use sunlight to synthesize nutrients from carbon dioxide and water.",
                    "Photosynthesis in plants generally involves the green pigment chlorophyll and generates oxygen as a byproduct.",
                    "The general equation of photosynthesis is: 6CO2 + 6H2O + Light Energy -> C6H12O6 + 6O2.",
                    "During this process, light energy is absorbed by chlorophyll in the chloroplasts of the plant cells and converted into chemical energy.",
                    "The light-dependent reactions happen in the thylakoid membranes where ATP and NADPH are produced by the action of light on chlorophyll.",
                    "The dark reactions or light-independent reactions (Calvin cycle) occur in the stroma of the chloroplast, where carbon dioxide is fixed to produce sugars like glucose."
                ],
                "Respiration": [
                    "Respiration is the process of releasing energy from food. Organisms perform cellular respiration to break down glucose and generate ATP.",
                    "Aerobic respiration requires oxygen and produces carbon dioxide, water, and 38 ATP molecules per glucose molecule.",
                    "Anaerobic respiration occurs in the absence of oxygen, yielding lactic acid in muscles or ethanol in yeast, with only 2 ATP molecules produced.",
                    "Respiration in plants occurs through stomata on leaves, lenticels on stems, and root surfaces in contact with soil."
                ]
            }
        }
    },
    {
        "filename": "Chemistry_Class10_Ch2.pdf",
        "url": "https://ncert.nic.in/textbook/pdf/keph101.pdf",
        "title": "Chemistry Class 10 - Acids & Bases",
        "board": "CBSE",
        "subject": "Chemistry",
        "grade": "10",
        "content": {
            "Chapter 2 Acids Bases and Salts": {
                "Acids and Bases": [
                    "Acids are chemical substances characterized by a sour taste, turning blue litmus red, and reacting with bases to form salts.",
                    "Common acids include hydrochloric acid (HCl), sulfuric acid (H2SO4), and nitric acid (HNO3).",
                    "Bases are substances that taste bitter, feel slippery, turn red litmus blue, and react with acids to form salts.",
                    "Common bases include sodium hydroxide (NaOH), potassium hydroxide (KOH), and calcium hydroxide (Ca(OH)2).",
                    "According to Arrhenius theory, acids release hydrogen ions (H+) in aqueous solution, while bases release hydroxide ions (OH-).",
                    "The pH scale measures the acidity or basicity of a solution, ranging from 0 to 14, where 7 is neutral, below 7 is acidic, and above 7 is basic."
                ],
                "Salts": [
                    "Salts are ionic compounds formed by the neutralization reaction of an acid and a base.",
                    "For example, hydrochloric acid reacts with sodium hydroxide to form sodium chloride (NaCl) and water.",
                    "Other examples of salts include copper sulfate, ammonium chloride, and sodium bicarbonate (baking soda).",
                    "Salts have high melting points and conduct electricity when dissolved in water or melted due to free ions."
                ]
            }
        }
    },
    {
        "filename": "Physics_Class10_Ch10.pdf",
        "url": "https://ncert.nic.in/textbook/pdf/keys101.pdf",
        "title": "Physics Class 10 - Electricity",
        "board": "CBSE",
        "subject": "Physics",
        "grade": "10",
        "content": {
            "Chapter 10 Electricity": {
                "Electric Current and Potential Difference": [
                    "Electric current is the rate of flow of electric charge through a conductor.",
                    "The SI unit of electric current is Ampere (A), measured using an instrument called an ammeter.",
                    "One Ampere is defined as the flow of one Coulomb of charge per second: I = Q / t.",
                    "Potential difference is the work done to move a unit charge from one point to another in an electric circuit.",
                    "The SI unit of potential difference is Volt (V), measured using a voltmeter: V = W / Q."
                ],
                "Ohms Law and Resistance": [
                    "Ohm's law states that the electric current flowing through a metallic conductor is directly proportional to the potential difference across its ends, provided its temperature remains constant.",
                    "Mathematically, V = I * R, where R is the resistance of the conductor. The SI unit of resistance is Ohm.",
                    "Resistance depends on the length of the conductor, its cross-sectional area, and the material's resistivity.",
                    "Resistors can be connected in series or parallel. In series, total resistance is Rs = R1 + R2 + R3.",
                    "In parallel, total resistance is 1/Rp = 1/R1 + 1/R2 + 1/R3."
                ]
            }
        }
    },
    {
        "filename": "Mathematics_Class10_Ch2.pdf",
        "url": "https://ncert.nic.in/textbook/pdf/kemh101.pdf",
        "title": "Mathematics Class 10 - Polynomials",
        "board": "CBSE",
        "subject": "Mathematics",
        "grade": "10",
        "content": {
            "Chapter 2 Polynomials": {
                "Introduction to Polynomials": [
                    "A polynomial is an algebraic expression consisting of variables and coefficients, involving operations of addition, subtraction, multiplication, and non-negative integer exponents.",
                    "The highest power of the variable in a polynomial is called its degree.",
                    "A polynomial of degree 1 is linear, degree 2 is quadratic, degree 3 is cubic.",
                    "The general form of a quadratic polynomial is ax^2 + bx + c, where a, b, c are real numbers and a is not equal to zero.",
                    "The values of x for which the polynomial becomes zero are called its zeroes."
                ],
                "Relationship between Zeroes and Coefficients": [
                    "For a quadratic polynomial ax^2 + bx + c, if alpha and beta are its zeroes, then the sum of zeroes is alpha + beta = -b/a, and the product of zeroes is alpha * beta = c/a.",
                    "For a cubic polynomial ax^3 + bx^2 + cx + d, the sum of zeroes is -b/a, the sum of product of zeroes taken two at a time is c/a, and the product of zeroes is -d/a."
                ]
            }
        }
    }
]

def download_file(url, dest_path):
    """Download a file with user-agent headers to avoid blocks."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        print(f"   Downloading: {url}...")
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        if response.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"   [OK] Successfully downloaded to {dest_path}")
            return True
        else:
            print(f"   [Warning] Download failed with status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"   [Warning] Download error: {e}")
        return False

def generate_pdf_stub(file_path, content):
    """Generate a valid PDF stub containing the chapter text using PyMuPDF."""
    if fitz is None:
        raise ImportError("fitz (PyMuPDF) is required to generate PDF stubs.")
        
    doc = fitz.open()
    
    # PDFParser detects headings based on font sizes:
    # Chapter >= 18, Section >= 14, Body = 10
    for chapter_name, sections in content.items():
        page = doc.new_page()
        
        # Draw Chapter heading
        page.insert_text((72, 72), f"CHAPTER: {chapter_name}", fontsize=20)
        
        y = 120
        for section_name, paragraphs in sections.items():
            if y > 700:
                page = doc.new_page()
                y = 72
                
            # Draw Section heading
            page.insert_text((72, y), f"SECTION: {section_name}", fontsize=15)
            y += 30
            
            for para in paragraphs:
                # Basic text wrapping
                words = para.split(" ")
                lines = []
                current_line = []
                for word in words:
                    if len(" ".join(current_line + [word])) > 80:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        current_line.append(word)
                if current_line:
                    lines.append(" ".join(current_line))
                
                for line in lines:
                    if y > 720:
                        page = doc.new_page()
                        y = 72
                    page.insert_text((72, y), line, fontsize=10)
                    y += 18
                y += 10
            y += 20
            
    doc.save(file_path)
    print(f"   [OK] Generated fallback stub PDF at {file_path}")

def main():
    init_db()
    TEXTBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for tb in TEXTBOOKS_INFO:
        filename = tb["filename"]
        dest_path = TEXTBOOKS_DIR / filename
        title = tb["title"]
        board = tb["board"]
        subject = tb["subject"]
        grade = tb["grade"]
        
        print(f"\n[Textbook] Processing: {title}")
        
        # Step 1: Download or Generate PDF
        success = False
        if not dest_path.exists():
            success = download_file(tb["url"], dest_path)
            
        if dest_path.exists():
            success = True
        else:
            print("   Creating high-quality mock PDF fallback using PyMuPDF...")
            try:
                generate_pdf_stub(dest_path, tb["content"])
                success = True
            except Exception as e:
                print(f"   [Error] Failed to generate stub PDF: {e}")
                continue
                
        if not success:
            print(f"   [Error] Skipping {title} due to missing PDF.")
            continue
            
        # Step 2: Ingest PDF into database
        try:
            # Check if textbook already exists in database
            cursor.execute("SELECT id FROM textbooks WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            if row:
                print(f"   [Info] Already exists in DB (textbook_id={row[0]}). Deleting and re-ingesting...")
                cursor.execute("DELETE FROM textbooks WHERE id = ?", (row[0],))
                conn.commit()
                
            parser = PDFParser(str(dest_path))
            parsed_pages = parser.parse()
            pdf_metadata = parser.get_metadata()
            
            chunker = Chunker(
                max_chunk_tokens=settings.CHUNK_MAX_TOKENS,
                overlap_tokens=settings.CHUNK_OVERLAP_TOKENS
            )
            chunks = chunker.chunk_by_section(parsed_pages)
            
            cursor.execute("""
                INSERT INTO textbooks
                (filename, title, board, subject, grade, total_pages, total_chunks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                filename,
                title or pdf_metadata.get("title", filename),
                board, subject, grade,
                len(parsed_pages), len(chunks)
            ))
            conn.commit()
            
            cursor.execute("SELECT last_insert_rowid()")
            textbook_id = cursor.fetchone()[0]
            
            # Insert chunks into database
            for chunk in chunks:
                chunk.textbook_id = textbook_id
                cursor.execute("""
                    INSERT INTO chunks
                    (textbook_id, chapter_number, chapter_title, section_title,
                     page_number, chunk_index, content, token_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk.textbook_id, chunk.chapter_number,
                    chunk.chapter_title, chunk.section_title,
                    chunk.page_number, chunk.chunk_index,
                    chunk.content, chunk.token_count
                ))
            conn.commit()
            
            # Generate and update embeddings
            embedder = Embedder()
            texts = [chunk.content for chunk in chunks]
            embeddings = embedder.embed_chunks(texts, show_progress=False)
            
            for chunk, embedding in zip(chunks, embeddings):
                embedding_bytes = embedding.astype('float32').tobytes()
                cursor.execute("""
                    UPDATE chunks SET embedding = ? WHERE textbook_id = ? AND chunk_index = ?
                """, (embedding_bytes, textbook_id, chunk.chunk_index))
            conn.commit()
            
            # Build ContextPruner indices (BM25, etc.)
            pruner = ContextPruner()
            pruner.setup_textbook(textbook_id)
            
            print(f"   [OK] Ingested successfully into DB (textbook_id={textbook_id}, {len(chunks)} chunks, {len(parsed_pages)} pages).")
            
        except Exception as e:
            print(f"   [Error] Ingestion error for {title}: {e}")
            import traceback
            traceback.print_exc()

    print("\n[Stats] Verification:")
    cursor.execute("SELECT id, title, subject, total_chunks FROM textbooks;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"   - ID: {row[0]} | Title: {row[1]} | Subject: {row[2]} | Chunks: {row[3]}")
        
    print("\n[Success] Done!")

if __name__ == "__main__":
    main()
