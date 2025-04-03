import os
import time
import uuid
import tempfile
import logging
import json
import pickle
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import PyPDF2
import google.generativeai as genai

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inicializar a aplicação Flask
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite de 16MB para upload

# Configuração da API Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB6rCSWCUmEtQFJT0CtwY_jvWl2oiYObVo")
genai.configure(api_key=GEMINI_API_KEY)

# Modelo Gemini a ser usado
MODEL = "gemini-2.0-flash"

# Diretório temporário para armazenamento de PDFs e critérios
TEMP_DIR = tempfile.gettempdir()
PDF_STORAGE_DIR = os.path.join(TEMP_DIR, "scianalyzer_pdfs")
CRITERIA_STORAGE_DIR = os.path.join(TEMP_DIR, "scianalyzer_criteria")
PDF_METADATA_DIR = os.path.join(TEMP_DIR, "scianalyzer_pdf_metadata")
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
os.makedirs(CRITERIA_STORAGE_DIR, exist_ok=True)
os.makedirs(PDF_METADATA_DIR, exist_ok=True)
logger.info(f"Diretório de armazenamento de PDFs: {PDF_STORAGE_DIR}")
logger.info(f"Diretório de armazenamento de critérios: {CRITERIA_STORAGE_DIR}")
logger.info(f"Diretório de armazenamento de metadados: {PDF_METADATA_DIR}")

# Função para salvar metadados do PDF
def save_pdf_metadata(pdf_id, metadata):
    try:
        metadata_file = os.path.join(PDF_METADATA_DIR, f"{pdf_id}.pickle")
        with open(metadata_file, 'wb') as f:
            pickle.dump(metadata, f)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar metadados do PDF {pdf_id}: {str(e)}")
        return False

# Função para carregar metadados do PDF
def load_pdf_metadata(pdf_id):
    try:
        metadata_file = os.path.join(PDF_METADATA_DIR, f"{pdf_id}.pickle")
        if not os.path.exists(metadata_file):
            return None
        
        with open(metadata_file, 'rb') as f:
            metadata = pickle.load(f)
        return metadata
    except Exception as e:
        logger.error(f"Erro ao carregar metadados do PDF {pdf_id}: {str(e)}")
        return None

# Função para verificar se um PDF existe
def pdf_exists(pdf_id):
    # Verificar se existe o arquivo de metadados
    metadata_file = os.path.join(PDF_METADATA_DIR, f"{pdf_id}.pickle")
    if not os.path.exists(metadata_file):
        return False
    
    # Carregar metadados para verificar o caminho do arquivo
    metadata = load_pdf_metadata(pdf_id)
    if not metadata or 'path' not in metadata:
        return False
    
    # Verificar se o arquivo PDF existe
    return os.path.exists(metadata['path'])

# Armazenamento temporário de PDFs
pdf_storage = {}

# Critérios de análise padrão
DEFAULT_CRITERIA = {
    "metodologia": "Avalie a metodologia utilizada no artigo, incluindo o design do estudo, amostragem, coleta de dados e análise estatística.",
    "resultados": "Analise os principais resultados e descobertas apresentados no artigo.",
    "conclusoes": "Avalie as conclusões do artigo e se elas são suportadas pelos resultados apresentados.",
    "limitacoes": "Identifique as limitações do estudo mencionadas pelos autores ou evidentes na metodologia.",
    "relevancia": "Avalie a relevância e contribuição do artigo para o campo de estudo.",
    "referencias": "Analise a qualidade e atualidade das referências utilizadas."
}

# Carregar critérios salvos ou usar os padrões
def load_criteria():
    criteria_file = os.path.join(CRITERIA_STORAGE_DIR, "criteria.json")
    if os.path.exists(criteria_file):
        try:
            with open(criteria_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar critérios: {str(e)}")
    return DEFAULT_CRITERIA.copy()

# Salvar critérios personalizados
def save_criteria(criteria):
    criteria_file = os.path.join(CRITERIA_STORAGE_DIR, "criteria.json")
    try:
        with open(criteria_file, 'w', encoding='utf-8') as f:
            json.dump(criteria, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar critérios: {str(e)}")
        return False

# Inicializar critérios
app.config['CRITERIA'] = load_criteria()

# Função para extrair texto de um PDF
def extract_text_from_pdf(pdf_file_path):
    text = ""
    
    # Método 1: PyPDF2 (método principal)
    try:
        logger.info(f"Tentando extrair texto com PyPDF2")
        with open(pdf_file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                text += reader.pages[page_num].extract_text() + "\n"
        
        if text.strip():
            logger.info(f"Texto extraído com sucesso usando PyPDF2")
            return text
    except Exception as e:
        logger.warning(f"Erro ao extrair texto com PyPDF2: {str(e)}")
    
    # Método 2: pdfminer.six
    try:
        logger.info(f"Tentando extrair texto com pdfminer.six")
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        text = pdfminer_extract_text(pdf_file_path)
        
        if text.strip():
            logger.info(f"Texto extraído com sucesso usando pdfminer.six")
            return text
    except Exception as e:
        logger.warning(f"Erro ao extrair texto com pdfminer.six: {str(e)}")
    
    # Método 3: Tentativa alternativa com PyPDF2 e configurações diferentes
    try:
        logger.info(f"Tentando método alternativo com PyPDF2")
        with open(pdf_file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file, strict=False)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                # Tentar extrair texto com diferentes configurações
                try:
                    page_text = page.extract_text()
                except:
                    try:
                        page_text = page.extract_text(0)
                    except:
                        page_text = ""
                text += page_text + "\n"
        
        if text.strip():
            logger.info(f"Texto extraído com sucesso usando método alternativo de PyPDF2")
            return text
    except Exception as e:
        logger.warning(f"Erro ao extrair texto com método alternativo de PyPDF2: {str(e)}")
    
    # Se nenhum método funcionou, retornar texto vazio
    logger.error(f"Todos os métodos de extração de texto falharam para o arquivo {pdf_file_path}")
    return ""

# Função para gerar resposta do Gemini
def generate_gemini_response(prompt, history=None):
    try:
        # Configurar o modelo
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 4096,
        }
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        
        model = genai.GenerativeModel(
            model_name=MODEL,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Instruções para o modelo
        system_instruction = """
        Você é um assistente especializado em análise de artigos científicos. 
        Sua tarefa é analisar o conteúdo do PDF fornecido e responder às perguntas do usuário de forma clara e objetiva.
        
        Se forem fornecidos critérios de análise, utilize-os para estruturar sua resposta, abordando cada critério especificado.
        
        Quando encontrar tabelas no texto, tente formatá-las de maneira organizada usando markdown.
        
        Suas respostas devem ser:
        1. Baseadas apenas no conteúdo do PDF fornecido
        2. Precisas e fundamentadas em evidências do texto
        3. Estruturadas de acordo com os critérios de análise (quando fornecidos)
        4. Formatadas em markdown para melhor legibilidade
        5. Concisas, mas completas
        
        Se não conseguir responder com base no conteúdo do PDF, informe isso claramente.
        """
        
        # Adicionar instruções do sistema ao prompt
        enhanced_prompt = f"{system_instruction}\n\n{prompt}"
        
        # Criar a conversa
        if history:
            # Se houver histórico, adicionar as mensagens anteriores
            convo = model.start_chat(history=history)
            response = convo.send_message(enhanced_prompt)
        else:
            # Se não houver histórico, iniciar uma nova conversa e enviar o prompt aprimorado
            convo = model.start_chat()
            response = convo.send_message(enhanced_prompt)
        
        return response.text
    
    except Exception as e:
        logger.error(f"Erro ao gerar resposta do Gemini: {str(e)}")
        return f"Desculpe, ocorreu um erro ao processar sua solicitação: {str(e)}"

# Rota principal
@app.route('/')
def index():
    return render_template('index.html')

# Rota para upload de PDF
@app.route('/upload', methods=['POST'])
def upload_pdf():
    try:
        # Verificar se o arquivo foi enviado
        if 'pdf' not in request.files:
            logger.error("Nenhum arquivo enviado na requisição de upload")
            return jsonify({"success": False, "error": "Nenhum arquivo enviado"})
        
        file = request.files['pdf']
        
        # Verificar se o arquivo tem nome
        if file.filename == '':
            logger.error("Arquivo sem nome enviado na requisição de upload")
            return jsonify({"success": False, "error": "Nenhum arquivo selecionado"})
        
        # Verificar se o arquivo é um PDF
        if not file.filename.lower().endswith('.pdf'):
            logger.error(f"Arquivo com extensão inválida enviado: {file.filename}")
            return jsonify({"success": False, "error": "Por favor, envie um arquivo PDF"})
        
        # Gerar ID único para o PDF
        pdf_id = str(uuid.uuid4())
        logger.info(f"Novo PDF ID gerado: {pdf_id} para o arquivo {file.filename}")
        
        # Salvar o arquivo
        filename = secure_filename(file.filename)
        file_path = os.path.join(PDF_STORAGE_DIR, f"{pdf_id}_{filename}")
        file.save(file_path)
        logger.info(f"Arquivo salvo em: {file_path}")
        
        # Verificar se o arquivo foi salvo corretamente
        if not os.path.exists(file_path):
            logger.error(f"Falha ao salvar o arquivo em: {file_path}")
            return jsonify({"success": False, "error": "Falha ao salvar o arquivo no servidor"})
        
        # Extrair texto do PDF
        pdf_text = extract_text_from_pdf(file_path)
        
        if not pdf_text or pdf_text.strip() == "":
            logger.error(f"Não foi possível extrair texto do PDF: {file_path}")
            os.remove(file_path)  # Remover arquivo se não conseguir extrair texto
            return jsonify({"success": False, "error": "Não foi possível extrair texto do PDF. Verifique se o arquivo não está corrompido ou protegido."})
        
        # Armazenar metadados do PDF
        metadata = {
            "text": pdf_text,
            "filename": filename,
            "timestamp": time.time(),
            "path": file_path
        }
        
        # Salvar metadados em arquivo
        if not save_pdf_metadata(pdf_id, metadata):
            logger.error(f"Falha ao salvar metadados do PDF {pdf_id}")
            os.remove(file_path)  # Remover arquivo se não conseguir salvar metadados
            return jsonify({"success": False, "error": "Falha ao processar o PDF no servidor"})
        
        logger.info(f"PDF armazenado com sucesso. ID: {pdf_id}, Tamanho do texto: {len(pdf_text)} caracteres")
        
        # Limpar PDFs antigos
        cleanup_old_pdfs()
        
        logger.info(f"PDF '{filename}' carregado com sucesso. ID: {pdf_id}")
        
        return jsonify({"success": True, "pdf_id": pdf_id, "filename": filename})
    
    except Exception as e:
        logger.error(f"Erro no upload: {str(e)}")
        return jsonify({"success": False, "error": f"Erro ao processar o arquivo: {str(e)}"})

# Rota para análise de artigo
@app.route('/analyze', methods=['POST'])
def analyze_article():
    try:
        data = request.json
        pdf_id = data.get('pdf_id')
        question = data.get('question')
        criteria = data.get('criteria', [])
        
        logger.info(f"Recebida requisição de análise. PDF ID: {pdf_id}")
        
        # Verificar se os parâmetros necessários foram fornecidos
        if not pdf_id:
            logger.error("ID do PDF não fornecido na requisição de análise")
            return jsonify({"success": False, "error": "ID do PDF não fornecido"})
        
        if not question:
            logger.error("Pergunta não fornecida na requisição de análise")
            return jsonify({"success": False, "error": "Pergunta não fornecida"})
        
        # Verificar se o PDF existe
        if not pdf_exists(pdf_id):
            logger.error(f"PDF ID {pdf_id} não encontrado")
            return jsonify({"success": False, "error": "PDF não encontrado. Por favor, faça o upload novamente."})
        
        # Carregar metadados do PDF
        metadata = load_pdf_metadata(pdf_id)
        if not metadata or 'text' not in metadata:
            logger.error(f"Metadados do PDF {pdf_id} não encontrados ou inválidos")
            return jsonify({"success": False, "error": "Dados do PDF não encontrados. Por favor, faça o upload novamente."})
        
        # Obter o texto do PDF
        pdf_text = metadata["text"]
        
        # Criar o prompt para análise
        prompt = create_analysis_prompt(pdf_text, question, criteria)
        print(prompt)
        
        # Gerar resposta
        response = generate_gemini_response(prompt)
        
        return jsonify({"success": True, "answer": response})
    
    except Exception as e:
        logger.error(f"Erro ao analisar artigo: {str(e)}")
        return jsonify({"success": False, "error": f"Erro ao analisar o artigo: {str(e)}"})

# Função para criar o prompt de análise
def create_analysis_prompt(pdf_text, question, criteria):
    criteria_text = "\n".join([f"- {c}" for c in criteria]) if criteria else "Não especificados"
    
    prompt = f"""Você é um assistente especializado em análise de artigos científicos.

Artigo para análise:
{pdf_text}

Critérios de análise especificados pelo usuário:
{criteria_text}

Pergunta do usuário: {question}

Por favor, analise o artigo científico acima com base nos critérios fornecidos e responda à pergunta do usuário.
Sua resposta deve ser detalhada, precisa e baseada apenas no conteúdo do artigo.
Se a pergunta não puder ser respondida com base no artigo, explique por quê.
Utilize markdown para formatar sua resposta quando apropriado."""
    
    return prompt

# Rota para chat em tempo real
@app.route('/chat', methods=['POST'])
def chat():
    try:
        # Obter dados da requisição
        data = request.json
        message = data.get('message', '')
        pdf_id = data.get('pdf_id')
        selected_criteria = data.get('criteria', {})
        is_analysis = data.get('is_analysis', False)
        
        logger.info(f"Recebida requisição de chat. PDF ID: {pdf_id}, Is Analysis: {is_analysis}")
        
        # Verificar se o ID do PDF foi fornecido
        if not pdf_id:
            logger.error("PDF ID não fornecido na requisição de chat")
            return jsonify({"success": False, "error": "PDF não encontrado. Por favor, faça upload novamente."})
        
        # Verificar se o PDF existe
        if not pdf_exists(pdf_id):
            logger.error(f"PDF ID {pdf_id} não encontrado")
            return jsonify({"success": False, "error": "PDF não encontrado. Por favor, faça upload novamente."})
        
        # Carregar metadados do PDF
        metadata = load_pdf_metadata(pdf_id)
        if not metadata or 'text' not in metadata:
            logger.error(f"Metadados do PDF {pdf_id} não encontrados ou inválidos")
            return jsonify({"success": False, "error": "Dados do PDF não encontrados. Por favor, faça upload novamente."})
        
        # Obter o texto do PDF
        pdf_text = metadata["text"]
        pdf_filename = metadata["filename"]
        
        # Verificar se o texto do PDF é válido
        if not pdf_text or pdf_text.strip() == "":
            logger.error(f"Texto do PDF {pdf_id} está vazio")
            return jsonify({"success": False, "error": "O texto extraído do PDF está vazio. Por favor, tente fazer upload novamente."})
        
        # Construir o prompt com base no tipo de solicitação (análise ou pergunta)
        if is_analysis:
            prompt = create_analysis_prompt_full(pdf_text, pdf_filename, selected_criteria)
        else:
            prompt = create_question_prompt(pdf_text, message, selected_criteria)
        
        # Gerar resposta
        response = generate_gemini_response(prompt)
        
        return jsonify({"success": True, "response": response})
    
    except Exception as e:
        logger.error(f"Erro no chat: {str(e)}")
        return jsonify({"success": False, "error": f"Erro ao processar mensagem: {str(e)}"})

# Função para criar o prompt de análise completa
def create_analysis_prompt_full(pdf_text, pdf_filename, criteria):
    prompt = f"""Faça uma análise completa e detalhada do seguinte artigo científico: '{pdf_filename}'.

Conteúdo do PDF:
{pdf_text}

"""
    
    if criteria:
        prompt += "Organize sua análise de acordo com os seguintes critérios:\n\n"
        for key, description in criteria.items():
            prompt += f"## {key.capitalize()}\n{description}\n\n"
    else:
        prompt += """Organize sua análise incluindo as seguintes seções:

## Resumo
Um resumo conciso do artigo.

## Metodologia
Análise da metodologia utilizada.

## Resultados Principais
Os principais resultados e descobertas.

## Conclusões
As conclusões do artigo e se são suportadas pelos resultados.

## Limitações
As limitações do estudo.

## Relevância
A relevância e contribuição para o campo.
"""
    
    prompt += """

Formate sua resposta utilizando markdown de forma elegante e moderna, seguindo estas diretrizes:

1. Use títulos (# e ##) para organizar as seções principais
2. Use subtítulos (### e ####) para temas dentro de cada seção
3. Utilize **negrito** para destacar conceitos-chave e termos importantes
4. Utilize *itálico* para ênfase moderada ou termos específicos
5. Crie listas com marcadores para enumerar pontos relacionados
6. Use listas numeradas para sequências ou passos
7. Quando citar dados numéricos, organize-os em tabelas bem formatadas
8. Utilize blocos de citação (>) para destacar trechos importantes do artigo
9. Separe seções com linhas horizontais (---) quando apropriado
10. Inclua um resumo conciso no início e uma conclusão ao final

Seja detalhado, mas conciso. Baseie sua análise apenas no conteúdo do PDF fornecido.
"""
    print(prompt)
    return prompt

# Função para criar o prompt de pergunta
def create_question_prompt(pdf_text, question, criteria):
    prompt = f"Pergunta do usuário: {question}\n\nConteúdo do PDF:\n{pdf_text}\n\n"
    
    if criteria:
        prompt += "\nConsidere os seguintes critérios de análise ao responder:\n"
        for key, description in criteria.items():
            prompt += f"- {key}: {description}\n"
    
    prompt += """

Formate sua resposta utilizando markdown de forma elegante e moderna, seguindo estas diretrizes:

1. Use títulos (# e ##) para organizar as seções principais
2. Use subtítulos (### e ####) para temas dentro de cada seção
3. Utilize **negrito** para destacar conceitos-chave e termos importantes
4. Utilize *itálico* para ênfase moderada ou termos específicos
5. Crie listas com marcadores para enumerar pontos relacionados
6. Use listas numeradas para sequências ou passos
7. Quando citar dados numéricos, organize-os em tabelas bem formatadas
8. Utilize blocos de citação (>) para destacar trechos importantes do artigo

Seja detalhado, mas conciso. Baseie sua resposta apenas no conteúdo do PDF fornecido.
"""
    
    return prompt

# Rota para obter critérios de análise
@app.route('/get-criteria', methods=['GET'])
def get_criteria():
    try:
        return jsonify({"success": True, "criteria": app.config['CRITERIA']})
    except Exception as e:
        logger.error(f"Erro ao obter critérios: {str(e)}")
        return jsonify({"success": False, "error": f"Erro ao obter critérios: {str(e)}"}), 500

# Rota para salvar um novo critério ou atualizar um existente
@app.route('/save-criteria', methods=['POST'])
def save_criteria_route():
    try:
        data = request.json
        key = data.get('key')
        description = data.get('description')
        
        if not key or not description:
            return jsonify({"success": False, "error": "Chave e descrição são obrigatórias"}), 400
        
        # Atualizar critério
        app.config['CRITERIA'][key] = description
        
        # Salvar no arquivo
        if save_criteria(app.config['CRITERIA']):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Erro ao salvar critério"}), 500
    
    except Exception as e:
        logger.error(f"Erro ao salvar critério: {str(e)}")
        return jsonify({"success": False, "error": f"Erro ao salvar critério: {str(e)}"}), 500

# Rota para excluir um critério
@app.route('/delete-criteria', methods=['POST'])
def delete_criteria():
    try:
        data = request.json
        key = data.get('key')
        
        if not key:
            return jsonify({"success": False, "error": "Chave do critério não fornecida"}), 400
        
        # Verificar se o critério existe
        if key not in app.config['CRITERIA']:
            return jsonify({"success": False, "error": "Critério não encontrado"}), 404
        
        # Remover critério
        del app.config['CRITERIA'][key]
        
        # Salvar no arquivo
        if save_criteria(app.config['CRITERIA']):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Erro ao excluir critério"}), 500
    
    except Exception as e:
        logger.error(f"Erro ao remover critério: {str(e)}")
        return jsonify({"success": False, "error": f"Error deleting criteria: {str(e)}"}), 500

# Função para limpar PDFs antigos (chamada periodicamente)
def cleanup_old_pdfs():
    try:
        current_time = time.time()
        expired_files = []
        
        # Listar todos os arquivos de metadados
        for filename in os.listdir(PDF_METADATA_DIR):
            if not filename.endswith('.pickle'):
                continue
                
            pdf_id = filename[:-7]  # Remover a extensão .pickle
            metadata_path = os.path.join(PDF_METADATA_DIR, filename)
            
            try:
                # Carregar metadados
                with open(metadata_path, 'rb') as f:
                    metadata = pickle.load(f)
                
                # Verificar se o PDF expirou (mais de 1 hora)
                if current_time - metadata.get("timestamp", 0) > 3600:  # 1 hora
                    expired_files.append((pdf_id, metadata.get("path"), metadata_path))
            except Exception as e:
                logger.error(f"Erro ao processar metadados {filename}: {str(e)}")
                # Adicionar arquivo de metadados corrompido à lista de expirados
                expired_files.append((pdf_id, None, metadata_path))
        
        # Remover PDFs expirados
        for pdf_id, pdf_path, metadata_path in expired_files:
            # Remover arquivo PDF se existir
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    logger.info(f"Arquivo PDF expirado removido: {pdf_path}")
                except Exception as e:
                    logger.error(f"Erro ao remover arquivo PDF {pdf_path}: {str(e)}")
            
            # Remover arquivo de metadados
            try:
                os.remove(metadata_path)
                logger.info(f"Metadados expirados removidos: {metadata_path}")
            except Exception as e:
                logger.error(f"Erro ao remover metadados {metadata_path}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Erro na limpeza de PDFs antigos: {str(e)}")

# Iniciar o servidor
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
