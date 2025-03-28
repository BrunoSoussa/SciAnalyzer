import os
import tempfile
import traceback
import json
import pickle
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import google.generativeai as genai
import PyPDF2
from werkzeug.utils import secure_filename
# Importar pdfminer.six para extração de texto alternativa
from io import StringIO
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
# Importar bibliotecas adicionais para tratamento robusto de PDFs
import re
import io
import logging
import unicodedata
import uuid
import time
import hashlib

app = Flask(__name__)
app.secret_key = 'secret_key_here'  # Add a secret key for session management
CORS(app)

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('scianalyzer')

# Diretorio para armazenar os arquivos de texto de PDF
PDF_STORAGE_DIR = os.path.join(tempfile.gettempdir(), 'scianalyzer_pdfs')
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
app.logger.info(f"Diretorio de armazenamento de PDFs: {PDF_STORAGE_DIR}")

# Dicionario para armazenar timestamps de quando os PDFs foram armazenados
pdf_timestamp_storage = {}

# Função para limpar PDFs antigos do armazenamento
def cleanup_old_pdfs():
    """Remove PDFs antigos do armazenamento para evitar vazamento de memória"""
    current_time = time.time()
    expired_ids = []
    
    # Identificar PDFs expirados
    for pdf_id, timestamp in pdf_timestamp_storage.items():
        if current_time - timestamp > 3600:  # 1 hora
            expired_ids.append(pdf_id)
    
    # Remover PDFs expirados
    for pdf_id in expired_ids:
        delete_pdf_text(pdf_id)
    
    if expired_ids:
        logger.info(f"Limpeza de armazenamento: {len(expired_ids)} PDFs antigos removidos")

def save_pdf_text(pdf_id, text):
    """Salva o texto do PDF em um arquivo temporário persistente"""
    try:
        file_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_id}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
        pdf_timestamp_storage[pdf_id] = time.time()
        app.logger.info(f"Texto do PDF salvo em {file_path}")
        return True
    except Exception as e:
        app.logger.error(f"Erro ao salvar texto do PDF: {str(e)}")
        return False

def get_pdf_text(pdf_id):
    """Recupera o texto do PDF de um arquivo temporário"""
    try:
        file_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_id}.txt")
        if not os.path.exists(file_path):
            app.logger.warning(f"Arquivo de texto do PDF não encontrado: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Atualizar o timestamp
        pdf_timestamp_storage[pdf_id] = time.time()
        return text
    except Exception as e:
        app.logger.error(f"Erro ao recuperar texto do PDF: {str(e)}")
        return None

def delete_pdf_text(pdf_id):
    """Remove o arquivo de texto do PDF"""
    try:
        file_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_id}.txt")
        if os.path.exists(file_path):
            os.remove(file_path)
            app.logger.info(f"Arquivo de texto do PDF removido: {file_path}")
        
        if pdf_id in pdf_timestamp_storage:
            del pdf_timestamp_storage[pdf_id]
        
        return True
    except Exception as e:
        app.logger.error(f"Erro ao remover arquivo de texto do PDF: {str(e)}")
        return False

def is_pdf_in_storage(pdf_id):
    """Verifica se o PDF existe no armazenamento"""
    file_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_id}.txt")
    return os.path.exists(file_path)

# Configure Gemini API with the provided key
API_KEY = "AIzaSyAgr6SVtn1tfrD_ynYO0eZKXaHQP8ONI28"
genai.configure(api_key=API_KEY)

# Usar o modelo Gemini mais recente
model = genai.GenerativeModel('gemini-2.0-flash')

# Definir limites de tokens mais adequados para artigos grandes
MAX_TOKENS_LIMIT = 600000  # Aumentado para acomodar artigos maiores
MAX_CHUNK_SIZE = 300000    # Tamanho máximo de cada chunk para processamento
PDF_STORAGE_TIMEOUT = 3600  # Tempo em segundos para expirar PDFs armazenados (1 hora)

# Função para limpar caracteres problemáticos do texto
def sanitize_text(text):
    """Limpa o texto removendo caracteres problemáticos e normalizando"""
    if not text:
        return ""
    
    try:
        # Substituir caracteres de controle por espaços, exceto quebras de linha
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
        
        # Normalizar caracteres Unicode
        text = unicodedata.normalize('NFKD', text)
        
        # Remover sequências de espaços extras
        text = re.sub(r'\s+', ' ', text)
        
        # Remover linhas vazias consecutivas
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        return text
    except Exception as e:
        app.logger.warning(f"Erro ao sanitizar texto: {str(e)}")
        # Retornar o texto original se houver erro na sanitização
        return text if text else ""

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file using multiple methods with robust error handling"""
    text = ""
    errors = []
    extraction_methods_tried = []
    
    # Função interna para registrar tentativas e erros
    def log_attempt(method_name, error=None):
        extraction_methods_tried.append(method_name)
        if error:
            error_msg = f"{method_name} falhou: {str(error)}"
            errors.append(error_msg)
            app.logger.warning(error_msg)
    
    # Método 1: Tentar com PyPDF2 (método principal)
    try:
        extraction_methods_tried.append("PyPDF2-full")
        app.logger.info(f"Tentando extrair texto com PyPDF2 de {pdf_file}")
        
        # Verificar se o arquivo é um PDF válido antes de tentar extrair
        try:
            # Tratamento específico para o erro '/Root'
            try:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
            except KeyError as ke:
                if '/Root' in str(ke):
                    app.logger.warning(f"Erro de estrutura PDF '/Root' - tentando com reparo")
                    # Usar uma abordagem alternativa para PDFs com erro /Root
                    from io import BytesIO
                    if hasattr(pdf_file, 'read'):
                        pdf_bytes = pdf_file.read()
                        pdf_file.seek(0)  # Reset file pointer
                    else:
                        with open(pdf_file, 'rb') as f:
                            pdf_bytes = f.read()
                    
                    # Tentar reparar o PDF corrompido (método 1)
                    try:
                        from PyPDF2 import PdfWriter
                        from PyPDF2.generic import NameObject
                        
                        memory_file = BytesIO(pdf_bytes)
                        writer = PdfWriter()
                        
                        # Tentar criar um novo PDF
                        try:
                            reader = PyPDF2.PdfReader(memory_file, strict=False)
                            for page in reader.pages:
                                writer.add_page(page)
                            
                            # Escrever o PDF reparado em memória
                            output_pdf = BytesIO()
                            writer.write(output_pdf)
                            output_pdf.seek(0)
                            
                            # Tentar ler o PDF reparado
                            pdf_reader = PyPDF2.PdfReader(output_pdf)
                        except Exception as repair_error:
                            app.logger.warning(f"Reparo 1 falhou: {str(repair_error)}")
                            raise
                    except Exception as repair_method_error:
                        app.logger.warning(f"Método de reparo 1 falhou: {str(repair_method_error)}")
                        # Tentar extrair texto de uma maneira alternativa sem reconstruir o PDF
                        raise
                else:
                    # Outros erros KeyError que não são '/Root'
                    raise
            
            # Verificar se o PDF tem uma estrutura válida
            if not hasattr(pdf_reader, "pages") or len(pdf_reader.pages) == 0:
                raise ValueError("PDF sem páginas válidas")
                
            # Extrair texto de todas as páginas
            full_text = ""
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n\n"
                except Exception as page_error:
                    app.logger.warning(f"Erro ao extrair texto da página {page_num}: {str(page_error)}")
                    # Continuar com outras páginas mesmo se uma falhar
            
            if full_text.strip():
                text = full_text
                app.logger.info(f"Extração PyPDF2 bem-sucedida: {len(text)} caracteres")
                return sanitize_text(text)  # Se bem-sucedido, retornar imediatamente
            else:
                log_attempt("PyPDF2-full", "Nenhum texto extraído")
        except KeyError as ke:
            # Lidar especificamente com o erro KeyError: '/Root'
            if "/Root" in str(ke):
                log_attempt("PyPDF2-full", f"Erro de estrutura PDF: {str(ke)}")
            else:
                log_attempt("PyPDF2-full", ke)
        except Exception as e:
            log_attempt("PyPDF2-full", e)
    except Exception as outer_e:
        log_attempt("PyPDF2-full", outer_e)
    
    # Método 2: Tentar com PyPDF2 página por página (fallback 1)
    if not text.strip():
        try:
            app.logger.info("Tentando extração com PyPDF2 página por página")
            
            # Resetar o ponteiro do arquivo se for um objeto arquivo
            if hasattr(pdf_file, 'seek'):
                pdf_file.seek(0)  # Reset file pointer
            
            try:
                # Tentar com configurações menos estritas
                pdf_reader = PyPDF2.PdfReader(pdf_file, strict=False)
                
                page_by_page_text = ""
                for i in range(len(pdf_reader.pages)):
                    try:
                        page = pdf_reader.pages[i]
                        page_text = page.extract_text()
                        if page_text:
                            page_by_page_text += page_text + "\n\n"
                    except Exception as page_error:
                        app.logger.warning(f"Erro ao extrair texto da página {i} (método página por página): {str(page_error)}")
                        # Continuar com outras páginas
                
                if page_by_page_text.strip():
                    text = page_by_page_text
                    app.logger.info(f"Extração PyPDF2 página por página bem-sucedida: {len(text)} caracteres")
                else:
                    log_attempt("PyPDF2-page-by-page", "Nenhum texto extraído")
            except Exception as pdf_error:
                app.logger.warning(f"Erro ao ler PDF página por página: {str(pdf_error)}")
                log_attempt("PyPDF2-page-by-page", pdf_error)
        except Exception as e:
            log_attempt("PyPDF2-page-by-page", e)
    
    # Método 3: Tentar com pdfminer.six (fallback 2)
    if not text.strip():
        try:
            app.logger.info("Tentando extração com pdfminer.six")
            from pdfminer.high_level import extract_text as pdfminer_extract_text
            
            # Resetar o ponteiro do arquivo se for um objeto arquivo
            if hasattr(pdf_file, 'seek'):
                pdf_file.seek(0)  # Reset file pointer
            
            pdfminer_text = ""
            
            try:
                # Tentar extrair o texto completo primeiro
                pdfminer_text = pdfminer_extract_text(pdf_file)
            except Exception as pm_error:
                app.logger.warning(f"Erro ao extrair texto completo com pdfminer: {str(pm_error)}")
                # Se falhar, tentar com configurações mais tolerantes
                try:
                    from pdfminer.high_level import extract_text_to_fp
                    from pdfminer.layout import LAParams
                    output_string = io.StringIO()
                    
                    # Resetar o ponteiro do arquivo se for um objeto arquivo
                    if hasattr(pdf_file, 'seek'):
                        pdf_file.seek(0)
                        
                    extract_text_to_fp(pdf_file, output_string, laparams=LAParams(char_margin=10.0, line_margin=0.5, word_margin=0.1))
                    pdfminer_text = output_string.getvalue()
                except Exception as pm_fallback_error:
                    log_attempt("pdfminer-fallback", pm_fallback_error)
            
            if pdfminer_text.strip():
                text = pdfminer_text
                app.logger.info(f"Extração pdfminer.six bem-sucedida: {len(text)} caracteres")
            else:
                log_attempt("pdfminer.six", "Nenhum texto extraído")
        except Exception as e:
            log_attempt("pdfminer.six", e)
    
    # Método 4: Extrair bytes de texto bruto como último recurso
    if not text.strip():
        try:
            app.logger.info("Tentando extração de texto bruto como último recurso")
            
            # Ler o conteúdo bruto do arquivo
            if hasattr(pdf_file, 'read') and hasattr(pdf_file, 'seek'):
                pdf_file.seek(0)
                raw_content = pdf_file.read()
            elif isinstance(pdf_file, str) and os.path.exists(pdf_file):
                with open(pdf_file, 'rb') as f:
                    raw_content = f.read()
            else:
                raw_content = b''
                log_attempt("raw-extraction", "Não foi possível ler o arquivo")
            
            if raw_content:
                # Procurar por strings de texto no arquivo bruto
                printable_chars = re.findall(b'[\x20-\x7E\n\r\t]+', raw_content)
                raw_text = b''.join(printable_chars).decode('utf-8', errors='ignore')
                
                # Filtrar o texto bruto para obter um resultado mais limpo
                filtered_lines = []
                for line in raw_text.split('\n'):
                    line = line.strip()
                    # Manter apenas linhas com texto significativo (pelo menos 20 caracteres ou contendo palavras-chave)
                    if len(line) >= 20 or re.search(r'abstract|introduction|conclusion|references|method', line.lower()):
                        filtered_lines.append(line)
                
                raw_text = '\n'.join(filtered_lines)
                
                if raw_text.strip():
                    text = raw_text
                    app.logger.info(f"Extração de texto bruto bem-sucedida: {len(text)} caracteres")
                else:
                    log_attempt("raw-extraction", "Texto extraído não contém conteúdo significativo")
            else:
                log_attempt("raw-extraction", "Sem conteúdo para extração")
        except Exception as e:
            log_attempt("raw-extraction", e)
    
    # Verificar se conseguimos extrair algum texto
    if not text.strip():
        error_message = f"Falha ao extrair texto do PDF. Métodos tentados: {', '.join(extraction_methods_tried)}. Erros: {'; '.join(errors)}"
        app.logger.error(error_message)
        raise Exception(error_message)
    
    # Sanitizar o texto antes de retornar
    sanitized_text = sanitize_text(text)
    app.logger.info(f"Texto extraído e sanitizado com sucesso: {len(sanitized_text)} caracteres")
    return sanitized_text

def process_large_text(text, max_size=MAX_CHUNK_SIZE):
    """Processa textos grandes dividindo em chunks ou resumindo conforme necessário"""
    if len(text) <= max_size:
        return text
    
    # Se o texto for maior que o limite, dividimos em partes importantes
    # Pegar o início (introdução, resumo, etc.)
    intro_size = max_size // 3
    intro = text[:intro_size]
    
    # Pegar o final (conclusões, resultados, etc.)
    conclusion_size = max_size // 3
    conclusion = text[-conclusion_size:]
    
    # Pegar uma parte do meio (desenvolvimento, métodos, etc.)
    middle_start = (len(text) - max_size // 3) // 2
    middle = text[middle_start:middle_start + max_size // 3]
    
    # Combinar as partes com uma nota explicativa
    processed_text = (
        f"{intro}\n\n"  
        f"[...CONTEÚDO INTERMEDIÁRIO OMITIDO PARA PROCESSAMENTO...]\n\n"
        f"{middle}\n\n"
        f"[...CONTEÚDO INTERMEDIÁRIO OMITIDO PARA PROCESSAMENTO...]\n\n"
        f"{conclusion}"
    )
    
    return processed_text

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "API is running"})

@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    # Executar limpeza de PDFs antigos
    cleanup_old_pdfs()
    
    # Gerar um novo ID para o PDF
    pdf_id = str(uuid.uuid4())
    pdf_timestamp_storage[pdf_id] = time.time()
    
    # Check if a file was uploaded
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    # Check if the file is a PDF
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Invalid or no PDF file provided"}), 400
    
    # Get the criteria from the request
    criteria_json = request.form.get('criteria', '[]')
    try:
        criteria = json.loads(criteria_json)
    except:
        criteria = []
    
    try:
        # Create a temporary file to store the PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp:
            file.save(temp.name)
            temp_filename = temp.name
        
        # Extract text from the PDF
        pdf_text = extract_text_from_pdf(temp_filename)
        
        # Store the PDF text in the storage dictionary
        save_pdf_text(pdf_id, pdf_text)
        
        # Clean up the temporary file
        os.unlink(temp_filename)
        
        # Check if any text was extracted
        if not pdf_text or pdf_text.strip() == "":
            # Limpar dados em caso de erro
            delete_pdf_text(pdf_id)
            return jsonify({"error": "No text could be extracted from the PDF. The file might be scanned or contain only images."}), 400
        
        # Verificar o tamanho do texto e processar conforme necessário
        original_length = len(pdf_text)
        was_truncated = False
        
        if len(pdf_text) > MAX_TOKENS_LIMIT:
            app.logger.info(f"PDF muito grande ({len(pdf_text)} caracteres). Processando para análise.")
            pdf_text = process_large_text(pdf_text)
            was_truncated = True
        
        # Create the prompt for scientific article analysis
        prompt = create_scientific_analysis_prompt(pdf_text, criteria)
        
        try:
            # Generate response from Gemini
            response = model.generate_content(prompt)
            
            return jsonify({
                "success": True,
                "criteria": criteria,
                "answer": response.text,
                "pdf_length": original_length,
                "has_pdf": True,
                "was_truncated": was_truncated,
                "pdf_id": pdf_id
            })
        except Exception as api_error:
            # Tentar novamente com um texto ainda menor se houver erro de API
            app.logger.warning(f"Erro na API Gemini: {str(api_error)}. Tentando com texto reduzido.")
            
            # Reduzir ainda mais o texto para uma segunda tentativa
            reduced_text = process_large_text(pdf_text, MAX_CHUNK_SIZE // 2)
            prompt = create_scientific_analysis_prompt(reduced_text, criteria)
            
            try:
                response = model.generate_content(prompt)
                
                return jsonify({
                    "success": True,
                    "criteria": criteria,
                    "answer": response.text,
                    "pdf_length": original_length,
                    "has_pdf": True,
                    "was_truncated": True,
                    "severely_truncated": True,
                    "pdf_id": pdf_id
                })
            except Exception as final_error:
                raise Exception(f"Falha ao processar o artigo mesmo após redução: {str(final_error)}")
        
    except Exception as e:
        # Limpar dados em caso de erro
        delete_pdf_text(pdf_id)
        
        app.logger.error(f"Error processing PDF: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500

@app.route('/chat', methods=['POST'])
def chat_with_article():
    # Executar limpeza de PDFs antigos
    cleanup_old_pdfs()
    
    data = request.json
    
    if not data or 'question' not in data:
        return jsonify({"error": "Missing question"}), 400
    
    question = data['question']
    app.logger.info(f"Recebida pergunta para chat: {question[:50]}...")
    
    # Obter o ID do PDF da requisição
    pdf_id = data.get('pdf_id', None)
    if not pdf_id:
        app.logger.warning(f"ID do PDF não fornecido na requisição de chat")
        return jsonify({"error": "Missing PDF ID"}), 400
    
    app.logger.info(f"Usando PDF ID para chat: {pdf_id}")
    
    # Verificar se o ID existe no armazenamento
    if not is_pdf_in_storage(pdf_id):
        app.logger.warning(f"ID do PDF {pdf_id} não encontrado no armazenamento")
        return jsonify({"error": "PDF not found. Please upload a PDF first."}), 400
    
    # Obter o texto do PDF do armazenamento
    pdf_text = get_pdf_text(pdf_id)
    
    # Verificar se temos algum texto de PDF para analisar
    if not pdf_text or pdf_text.strip() == "":
        app.logger.warning("Tentativa de chat sem PDF carregado (texto vazio)")
        return jsonify({"error": "No article content found. Please upload a PDF first."}), 400
    
    # Atualizar timestamp para evitar que o PDF expire durante o chat
    pdf_timestamp_storage[pdf_id] = time.time()
    app.logger.info(f"PDF encontrado com {len(pdf_text)} caracteres")
    
    try:
        # Processar o texto se for muito grande
        original_length = len(pdf_text)
        if len(pdf_text) > MAX_CHUNK_SIZE:
            app.logger.info(f"Reduzindo texto para chat: {len(pdf_text)} caracteres")
            pdf_text = process_large_text(pdf_text)
        
        # Create the prompt for article chat
        prompt = f"""You are an expert scientific article analyst. Based on the following scientific article, please answer this question: {question}\n\nARTICLE CONTENT:\n{pdf_text} always respond in ptbr """
        
        try:
            # Generate response from Gemini
            app.logger.info("Enviando pergunta para Gemini API")
            start_time = time.time()
            response = model.generate_content(prompt)
            elapsed = time.time() - start_time
            app.logger.info(f"Resposta recebida em {elapsed:.2f} segundos")
            
            return jsonify({
                "success": True,
                "question": question,
                "answer": response.text
            })
        except Exception as api_error:
            # Tentar novamente com um texto ainda menor se houver erro de API
            app.logger.warning(f"Erro na API Gemini durante chat: {str(api_error)}. Tentando com texto reduzido.")
            
            # Reduzir ainda mais o texto para uma segunda tentativa
            reduced_text = process_large_text(pdf_text, MAX_CHUNK_SIZE // 2)
            prompt = f"""You are an expert scientific article analyst. Based on the following scientific article, please answer this question: {question}\n\nARTICLE CONTENT:\n{reduced_text} always respond in ptbr """
            
            try:
                app.logger.info("Tentando novamente com texto ainda mais reduzido")
                start_time = time.time()
                response = model.generate_content(prompt)
                elapsed = time.time() - start_time
                app.logger.info(f"Resposta com texto reduzido recebida em {elapsed:.2f} segundos")
                
                return jsonify({
                    "success": True,
                    "question": question,
                    "answer": response.text,
                    "severely_truncated": True
                })
            except Exception as final_error:
                app.logger.error(f"Falha final na API Gemini durante chat: {str(final_error)}")
                raise Exception(f"Falha ao processar a pergunta mesmo após redução de texto: {str(final_error)}")
        
    except Exception as e:
        app.logger.error(f"Erro no endpoint de chat: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Error processing question: {str(e)}"}), 500

@app.route('/check-pdf-status', methods=['GET'])
def check_pdf_status():
    # Executar limpeza de PDFs antigos
    cleanup_old_pdfs()
    
    # Verificar se temos um ID no armazenamento temporário
    pdf_id = request.args.get('pdf_id', None)
    app.logger.info(f"Verificando status do PDF com ID: {pdf_id if pdf_id else 'Nenhum ID fornecido'}")
    
    # Se não tiver ID na requisição mas tiver na sessão, usar o da sessão
    if not pdf_id and 'pdf_id' in session:
        pdf_id = session.get('pdf_id')
        app.logger.info(f"Usando ID do PDF da sessão: {pdf_id}")
    
    if not pdf_id:
        app.logger.info("Nenhum ID de PDF disponível")
        return jsonify({
            "success": False,
            "pdf_uploaded": False,
            "message": "Nenhum ID de PDF fornecido"
        })
    
    # Verificar se o PDF existe no armazenamento
    pdf_exists = is_pdf_in_storage(pdf_id)
    
    if pdf_exists:
        app.logger.info(f"PDF encontrado com ID: {pdf_id}")
        # Atualizar o timestamp para evitar que o PDF seja removido durante a sessão do usuário
        pdf_timestamp_storage[pdf_id] = time.time()
        
        # Recuperar nome do arquivo se disponível
        filename = session.get('filename', None)
        
        return jsonify({
            "success": True,
            "pdf_uploaded": True,
            "pdf_id": pdf_id,
            "filename": filename,
            "message": "PDF encontrado",
            "summary": session.get('summary', "")
        })
    else:
        app.logger.warning(f"PDF com ID {pdf_id} não encontrado no armazenamento")
        # Limpar o ID da sessão se não encontrarmos o PDF
        if 'pdf_id' in session:
            session.pop('pdf_id')
        
        return jsonify({
            "success": False,
            "pdf_uploaded": False,
            "message": "PDF não encontrado no armazenamento"
        })

@app.route('/clear-pdf', methods=['POST'])
def clear_pdf():
    # Obter o ID do PDF da requisição
    data = request.json
    pdf_id = data.get('pdf_id', None)
    if not pdf_id:
        return jsonify({"error": "Missing PDF ID"}), 400
    
    # Limpar o texto do PDF do armazenamento
    if pdf_id in pdf_timestamp_storage:
        delete_pdf_text(pdf_id)
        app.logger.info("Dados do PDF limpos com sucesso")
    
    return jsonify({
        "success": True,
        "message": "PDF data cleared successfully"
    })

@app.route('/upload', methods=['POST'])
def upload_pdf():
    # Executar limpeza de PDFs antigos
    cleanup_old_pdfs()
    
    if 'pdfFile' not in request.files:
        app.logger.warning("Tentativa de upload sem arquivo")
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['pdfFile']
    
    if file.filename == '':
        app.logger.warning("Tentativa de upload com nome de arquivo vazio")
        return jsonify({"error": "No selected file"}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        app.logger.warning(f"Tentativa de upload de arquivo não-PDF: {file.filename}")
        return jsonify({"error": "File must be a PDF"}), 400
    
    try:
        # Gerar um ID único para este PDF
        pdf_id = str(uuid.uuid4())
        app.logger.info(f"Processando upload de PDF. ID gerado: {pdf_id}")

        # Criar um arquivo temporário para armazenar o PDF
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        file.save(temp_file.name)
        temp_file.close()
        
        app.logger.info(f"PDF salvo temporariamente em {temp_file.name}")
        
        # Extrair e processar o texto do PDF
        extracted_text = extract_text_from_pdf(temp_file.name)
        
        # Salvar o texto extraído e o timestamp no armazenamento
        save_pdf_text(pdf_id, extracted_text)
        pdf_timestamp_storage[pdf_id] = time.time()
        
        # Salvar o ID do PDF e o nome do arquivo na sessão
        session['pdf_id'] = pdf_id
        session['filename'] = file.filename

        # Limpar arquivo temporário
        os.unlink(temp_file.name)
        
        # Resumir o conteúdo do artigo para apresentar na interface
        return jsonify({
            "success": True,
            "pdf_id": pdf_id,
            "filename": file.filename,
            "message": "PDF uploaded successfully"
        })
    except Exception as e:
        app.logger.error(f"Erro no upload de PDF: {str(e)}")
        return jsonify({"error": f"Error uploading PDF: {str(e)}"}), 500

@app.route('/analyze-existing', methods=['POST'])
def analyze_existing_pdf():
    # Executar limpeza de PDFs antigos
    cleanup_old_pdfs()
    
    try:
        data = request.json
        
        # Verificar se temos os dados necessarios
        if not data or 'pdf_id' not in data or 'criteria' not in data:
            app.logger.warning("Tentativa de analise com dados incompletos")
            return jsonify({"error": "Missing required data (pdf_id or criteria)"}), 400
        
        pdf_id = data['pdf_id']
        selected_criteria = data['criteria']
        
        # Verificar se o PDF existe no armazenamento
        if not is_pdf_in_storage(pdf_id):
            app.logger.warning(f"ID do PDF {pdf_id} não encontrado para análise")
            return jsonify({"error": "PDF not found. Please upload a PDF first."}), 400
        
        # Recuperar o texto do PDF
        pdf_text = get_pdf_text(pdf_id)
        
        if not pdf_text or pdf_text.strip() == "":
            app.logger.warning(f"PDF {pdf_id} encontrado mas sem texto")
            return jsonify({"error": "No text found in the uploaded PDF."}), 400
        
        # Atualizar o timestamp para evitar que o PDF expire durante a análise
        pdf_timestamp_storage[pdf_id] = time.time()
        
        # Processar o texto se for muito grande
        original_length = len(pdf_text)
        was_truncated = False
        severely_truncated = False
        
        if len(pdf_text) > MAX_CHUNK_SIZE:
            app.logger.info(f"Reduzindo texto de {len(pdf_text)} caracteres para análise")
            pdf_text = process_large_text(pdf_text)
            was_truncated = True
            
            # Verificar se ainda precisa de mais redução
            if len(pdf_text) > MAX_CHUNK_SIZE:
                app.logger.warning(f"Reduzindo ainda mais o texto para {MAX_CHUNK_SIZE // 2} caracteres")
                pdf_text = process_large_text(pdf_text, MAX_CHUNK_SIZE // 2)
                severely_truncated = True
        
        # Criar o prompt para análise com base nos critérios selecionados
        prompt = create_scientific_analysis_prompt(pdf_text, selected_criteria)
        
        try:
            # Gerar respostas do Gemini
            app.logger.info("Enviando prompt de análise para Gemini API")
            start_time = time.time()
            response = model.generate_content(prompt)
            elapsed = time.time() - start_time
            app.logger.info(f"Resposta recebida em {elapsed:.2f} segundos")
            
            # Armazenar o resumo na sessão para acesso futuro
            session['summary'] = response.text
            
            return jsonify({
                "success": True,
                "pdf_id": pdf_id,
                "answer": response.text,
                "was_truncated": was_truncated,
                "severely_truncated": severely_truncated,
                "pdf_length": original_length
            })
            
        except Exception as api_error:
            app.logger.error(f"Erro na API Gemini: {str(api_error)}")
            return jsonify({"error": f"Error in AI processing: {str(api_error)}"}), 500
            
    except Exception as e:
        app.logger.error(f"Erro ao analisar PDF existente: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Error analyzing PDF: {str(e)}"}), 500

def create_scientific_analysis_prompt(pdf_text, criteria):
    """Create a prompt for scientific article analysis based on selected criteria"""
    
    # Define the evaluation criteria descriptions
    criteria_descriptions = {
        "title": "Avalie se o título identifica claramente que se trata de uma revisão não sistemática (se aplicável).",
        "abstract": "Avalie se o resumo contém todos os elementos essenciais: objetivo, métodos, resultados e conclusão.",
        "introduction": "Avalie se o problema é bem definido, se justifica a importância da revisão e se os objetivos estão bem formulados.",
        "eligibility": "Avalie se o artigo descreve os critérios de inclusão e exclusão dos estudos.",
        "info_sources": "Avalie se o artigo indica todas as bases de dados utilizadas e período da pesquisa.",
        "search_strategy": "Avalie se o artigo apresenta a estratégia de busca de forma clara e replicável (se aplicável).",
        "selection_process": "Avalie se o artigo explica como os estudos foram selecionados (ex: número de revisores, etapas)."
    }
    
    # Build the prompt based on selected criteria
    selected_criteria_text = ""
    for criterion in criteria:
        if criterion in criteria_descriptions:
            selected_criteria_text += f"- {criteria_descriptions[criterion]}\n"
    
    if not selected_criteria_text:
        selected_criteria_text = "Faça uma análise geral do artigo científico, avaliando sua qualidade metodológica e contribuição para o campo."
    
    prompt = f"""Você é um especialista em análise de artigos científicos. Por favor, analise o seguinte artigo científico de acordo com os critérios solicitados.\n\n
    CRITÉRIOS DE AVALIAÇÃO:\n{selected_criteria_text}\n\n
    Para cada critério, indique se foi cumprido (Sim/Não/Parcialmente) e forneça observações detalhadas justificando sua avaliação.\n\n
    Apresente sua análise em formato de tabela com exatamente 4 colunas:\n
    | Item Avaliado | Descrição | Cumprido | Observações |\n
    Mantenha a tabela organizada e com tamanho de colunas consistente. Não use linhas de separação entre as linhas da tabela.\n\n
    Após a tabela, forneça uma análise geral do artigo com pontos fortes e fracos, e recomendações para melhoria.\n\n
    Use o seguinte formato para a análise após a tabela:\n
    **Análise Geral:**\n\n
    **Pontos Fortes:**\n
    * Ponto 1\n
    * Ponto 2\n\n
    **Pontos Fracos:**\n
    * Ponto 1\n
    * Ponto 2\n\n
    **Recomendações:**\n
    * Recomendação 1\n
    * Recomendação 2\n\n
    ARTIGO CIENTÍFICO:\n{pdf_text}"""
    
    return prompt

# Executar limpeza periódica
def periodic_cleanup():
    while True:
        cleanup_old_pdfs()
        time.sleep(PDF_STORAGE_TIMEOUT)

import threading
threading.Thread(target=periodic_cleanup).start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
