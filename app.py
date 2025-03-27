import os
import tempfile
import traceback
import json
from flask import Flask, request, jsonify, render_template
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

app = Flask(__name__)
CORS(app)

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('scianalyzer')

# Dicionário para armazenar o texto do PDF mais recente
pdf_text_storage = {}
# Dicionário para armazenar timestamps de quando os PDFs foram armazenados
pdf_timestamp_storage = {}

# Configure Gemini API with the provided key
API_KEY = "AIzaSyAgr6SVtn1tfrD_ynYO0eZKXaHQP8ONI28"
genai.configure(api_key=API_KEY)

# Usar o modelo Gemini mais recente
model = genai.GenerativeModel('gemini-2.0-flash')

# Definir limites de tokens mais adequados para artigos grandes
MAX_TOKENS_LIMIT = 60000  # Aumentado para acomodar artigos maiores
MAX_CHUNK_SIZE = 30000    # Tamanho máximo de cada chunk para processamento
PDF_STORAGE_TIMEOUT = 3600  # Tempo em segundos para expirar PDFs armazenados (1 hora)

# Função para limpar PDFs antigos do armazenamento
def cleanup_old_pdfs():
    """Remove PDFs antigos do armazenamento para evitar vazamento de memória"""
    current_time = time.time()
    expired_ids = []
    
    # Identificar PDFs expirados
    for pdf_id, timestamp in pdf_timestamp_storage.items():
        if current_time - timestamp > PDF_STORAGE_TIMEOUT:
            expired_ids.append(pdf_id)
    
    # Remover PDFs expirados
    for pdf_id in expired_ids:
        if pdf_id in pdf_text_storage:
            del pdf_text_storage[pdf_id]
        if pdf_id in pdf_timestamp_storage:
            del pdf_timestamp_storage[pdf_id]
    
    if expired_ids:
        logger.info(f"Limpeza de armazenamento: {len(expired_ids)} PDFs antigos removidos")

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
    """Extract text content from a PDF file using multiple methods for robustness"""
    text = ""
    errors = []
    
    # Método 1: Tentar com PyPDF2 primeiro
    try:
        app.logger.info(f"Tentando extrair texto com PyPDF2 de {pdf_file}")
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        pdf_text = ""
        
        # Processar cada página individualmente para maior robustez
        for page_num in range(len(pdf_reader.pages)):
            try:
                page_text = pdf_reader.pages[page_num].extract_text()
                if page_text:
                    # Sanitizar o texto da página antes de adicionar
                    pdf_text += sanitize_text(page_text) + "\n\n"
            except Exception as page_error:
                app.logger.warning(f"Erro ao extrair texto da página {page_num}: {str(page_error)}")
                # Continuar com a próxima página mesmo se esta falhar
                continue
        
        if pdf_text.strip():
            app.logger.info("Extração com PyPDF2 bem-sucedida")
            return pdf_text
    except Exception as e:
        error_msg = f"Erro ao extrair texto com PyPDF2: {str(e)}"
        app.logger.warning(error_msg)
        errors.append(error_msg)
    
    # Método 2: Se PyPDF2 falhar, tentar com pdfminer.six
    try:
        app.logger.info(f"Tentando extrair texto com pdfminer.six de {pdf_file}")
        output_string = StringIO()
        
        # Configurar parâmetros mais tolerantes para pdfminer
        laparams = LAParams(
            char_margin=2.0,  # Aumentar margem entre caracteres
            line_margin=0.5,  # Aumentar margem entre linhas
            word_margin=0.1,  # Aumentar margem entre palavras
            detect_vertical=True,  # Detectar texto vertical
            all_texts=True  # Extrair todos os textos, mesmo os que parecem decorativos
        )
        
        with open(pdf_file, 'rb') as pdf_file_obj:
            try:
                extract_text_to_fp(pdf_file_obj, output_string, laparams=laparams, 
                                codec='utf-8')
                text = output_string.getvalue()
                # Sanitizar o texto extraído
                text = sanitize_text(text)
                
                if text.strip():
                    app.logger.info("Extração com pdfminer.six bem-sucedida")
                    return text
            except Exception as inner_error:
                app.logger.warning(f"Erro durante extração com pdfminer: {str(inner_error)}")
                # Tentar extrair página por página se falhar a extração completa
                try:
                    from pdfminer.pdfpage import PDFPage
                    from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
                    from pdfminer.converter import TextConverter
                    
                    text = ""
                    resource_manager = PDFResourceManager()
                    
                    # Voltar ao início do arquivo
                    pdf_file_obj.seek(0)
                    
                    # Processar página por página
                    for page in PDFPage.get_pages(pdf_file_obj, check_extractable=False):
                        try:
                            output = StringIO()
                            converter = TextConverter(resource_manager, output, laparams=laparams)
                            interpreter = PDFPageInterpreter(resource_manager, converter)
                            interpreter.process_page(page)
                            
                            page_text = output.getvalue()
                            text += sanitize_text(page_text) + "\n\n"
                            
                            converter.close()
                            output.close()
                        except Exception as page_error:
                            app.logger.warning(f"Erro ao processar página individual: {str(page_error)}")
                            continue
                    
                    if text.strip():
                        app.logger.info("Extração página por página bem-sucedida")
                        return text
                except Exception as detailed_error:
                    app.logger.warning(f"Falha na extração página por página: {str(detailed_error)}")
    except Exception as e:
        error_msg = f"Erro ao extrair texto com pdfminer.six: {str(e)}"
        app.logger.warning(error_msg)
        errors.append(error_msg)
    
    # Método 3: Tentar extrair texto bruto como último recurso
    try:
        app.logger.info("Tentando extração de texto bruto como último recurso")
        with open(pdf_file, 'rb') as pdf_file_obj:
            content = pdf_file_obj.read()
            
            # Procurar por strings de texto no arquivo bruto
            printable_chars = re.findall(b'[\x20-\x7E\n\r\t]+', content)
            raw_text = b''.join(printable_chars).decode('utf-8', errors='ignore')
            
            # Limpar o texto bruto
            raw_text = sanitize_text(raw_text)
            
            # Remover linhas muito curtas que provavelmente são lixo
            raw_text = '\n'.join([line for line in raw_text.split('\n') if len(line.strip()) > 3])
            
            if raw_text.strip():
                app.logger.info("Extração de texto bruto bem-sucedida")
                return raw_text
    except Exception as e:
        error_msg = f"Erro na extração de texto bruto: {str(e)}"
        app.logger.warning(error_msg)
        errors.append(error_msg)
    
    # Se chegamos aqui, todos os métodos falharam, mas vamos retornar qualquer texto que tenhamos conseguido
    if text and text.strip():
        app.logger.warning("Retornando texto parcial após falhas nos métodos principais")
        return text
    
    # Se realmente não conseguimos nada, lançar exceção
    error_details = "\n".join(errors)
    app.logger.error(f"Falha em todos os métodos de extração de texto. Detalhes: {error_details}")
    raise Exception(f"Não foi possível extrair texto do PDF. O arquivo pode estar corrompido ou protegido.")

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
    pdf_text_storage[pdf_id] = ""
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
        pdf_text_storage[pdf_id] = pdf_text
        pdf_timestamp_storage[pdf_id] = time.time()  # Atualizar timestamp
        
        # Clean up the temporary file
        os.unlink(temp_filename)
        
        # Check if any text was extracted
        if not pdf_text or pdf_text.strip() == "":
            # Limpar dados em caso de erro
            pdf_text_storage[pdf_id] = ""
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
        pdf_text_storage[pdf_id] = ""
        
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
        return jsonify({"error": "Missing PDF ID"}), 400
    
    # Obter o texto do PDF do armazenamento
    pdf_text = pdf_text_storage.get(pdf_id, None)
    
    # Verificar se temos algum texto de PDF para analisar
    if not pdf_text or pdf_text.strip() == "":
        app.logger.warning("Tentativa de chat sem PDF carregado")
        return jsonify({"error": "No article context found. Please upload a PDF first."}), 400
    
    # Atualizar timestamp para evitar que o PDF expire durante o chat
    pdf_timestamp_storage[pdf_id] = time.time()
    
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
    
    # Obter o ID do PDF da requisição
    pdf_id = request.args.get('pdf_id', None)
    if not pdf_id:
        return jsonify({"error": "Missing PDF ID"}), 400
    
    # Verificar se temos um PDF carregado no armazenamento
    pdf_text = pdf_text_storage.get(pdf_id, None)
    
    has_pdf = bool(pdf_text and pdf_text.strip() != "")
    
    # Garantir que has_pdf é False se não houver texto de PDF válido
    if not has_pdf and pdf_id in pdf_text_storage:
        # Limpar qualquer dado residual
        pdf_text_storage[pdf_id] = ""
        if pdf_id in pdf_timestamp_storage:
            del pdf_timestamp_storage[pdf_id]
        app.logger.info("Status do PDF: Nenhum PDF carregado")
    elif has_pdf:
        # Atualizar timestamp para evitar que o PDF expire durante a verificação
        pdf_timestamp_storage[pdf_id] = time.time()
        app.logger.info(f"Status do PDF: PDF carregado com {len(pdf_text)} caracteres")
    
    return jsonify({
        "has_pdf": has_pdf
    })

@app.route('/clear-pdf', methods=['POST'])
def clear_pdf():
    # Obter o ID do PDF da requisição
    data = request.json
    pdf_id = data.get('pdf_id', None)
    if not pdf_id:
        return jsonify({"error": "Missing PDF ID"}), 400
    
    # Limpar o texto do PDF do armazenamento
    if pdf_id in pdf_text_storage:
        pdf_text_storage[pdf_id] = ""
        if pdf_id in pdf_timestamp_storage:
            del pdf_timestamp_storage[pdf_id]
        app.logger.info("Dados do PDF limpos com sucesso")
    
    return jsonify({
        "success": True,
        "message": "PDF data cleared successfully"
    })

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
