import os
import tempfile
import traceback
import json
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import google.generativeai as genai
import PyPDF2
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "analisador_artigos_cientificos_2025"  # Chave fixa para sessões mais estáveis
CORS(app)

# Variável global para armazenar o texto do PDF mais recente
pdf_text_storage = ""

# Configure Gemini API with the provided key
API_KEY = "AIzaSyAgr6SVtn1tfrD_ynYO0eZKXaHQP8ONI28"
genai.configure(api_key=API_KEY)

# Set up the model
model = genai.GenerativeModel('gemini-2.0-flash')

def extract_text_from_pdf(pdf_file):
    """Extract text content from a PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            page_text = pdf_reader.pages[page_num].extract_text()
            if page_text:
                text += page_text + "\n\n"
        return text
    except Exception as e:
        app.logger.error(f"Error extracting text from PDF: {str(e)}")
        raise

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "API is running"})

@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    global pdf_text_storage
    
    # Clear previous PDF text storage
    pdf_text_storage = ""
    session.pop('pdf_text', None)
    
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
        
        # Store the PDF text in both session and global variable
        session['pdf_text'] = pdf_text
        pdf_text_storage = pdf_text  # Armazenar em variável global também
        
        # Clean up the temporary file
        os.unlink(temp_filename)
        
        # Check if any text was extracted
        if not pdf_text or pdf_text.strip() == "":
            # Limpar dados em caso de erro
            pdf_text_storage = ""
            session.pop('pdf_text', None)
            return jsonify({"error": "No text could be extracted from the PDF. The file might be scanned or contain only images."}), 400
        
        # If the PDF text is too long, truncate it to avoid exceeding Gemini's token limit
        max_tokens = 30000  # Approximate token limit for Gemini Pro
        if len(pdf_text) > max_tokens:
            pdf_text = pdf_text[:max_tokens] + "\n[Content truncated due to length]\n"
        
        # Create the prompt for scientific article analysis
        prompt = create_scientific_analysis_prompt(pdf_text, criteria)
        
        # Generate response from Gemini
        response = model.generate_content(prompt)
        
        return jsonify({
            "success": True,
            "criteria": criteria,
            "answer": response.text,
            "pdf_length": len(pdf_text),
            "has_pdf": True
        })
        
    except Exception as e:
        # Limpar dados em caso de erro
        pdf_text_storage = ""
        session.pop('pdf_text', None)
        
        app.logger.error(f"Error processing PDF: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500

@app.route('/chat', methods=['POST'])
def chat_with_article():
    global pdf_text_storage
    
    data = request.json
    
    if not data or 'question' not in data:
        return jsonify({"error": "Missing question"}), 400
    
    question = data['question']
    
    # Tentar obter o texto do PDF da sessão primeiro
    pdf_text = session.get('pdf_text', None)
    
    # Se não estiver na sessão, usar a variável global
    if not pdf_text or pdf_text.strip() == "":
        pdf_text = pdf_text_storage
    
    # Verificar se temos algum texto de PDF para analisar
    if not pdf_text or pdf_text.strip() == "":
        return jsonify({"error": "No article context found. Please upload a PDF first."}), 400
    
    try:
        # Create the prompt for article chat
        prompt = f"""You are an expert scientific article analyst. Based on the following scientific article, please answer this question: {question}\n\nARTICLE CONTENT:\n{pdf_text} always respond in ptbr """
        
        # Generate response from Gemini
        response = model.generate_content(prompt)
        
        return jsonify({
            "success": True,
            "question": question,
            "answer": response.text
        })
        
    except Exception as e:
        app.logger.error(f"Error in chat endpoint: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Error processing question: {str(e)}"}), 500

@app.route('/check-pdf-status', methods=['GET'])
def check_pdf_status():
    global pdf_text_storage
    
    # Verificar se temos um PDF carregado na sessão ou na variável global
    pdf_text = session.get('pdf_text', None)
    
    if not pdf_text or pdf_text.strip() == "":
        pdf_text = pdf_text_storage
    
    has_pdf = bool(pdf_text and pdf_text.strip() != "")
    
    # Garantir que has_pdf é False se não houver texto de PDF válido
    if not has_pdf:
        # Limpar qualquer dado residual
        pdf_text_storage = ""
        session.pop('pdf_text', None)
    
    return jsonify({
        "has_pdf": has_pdf
    })

@app.route('/clear-pdf', methods=['POST'])
def clear_pdf():
    global pdf_text_storage
    
    # Clear PDF text from both session and global variable
    pdf_text_storage = ""
    session.pop('pdf_text', None)
    
    # Garantir que a sessão seja salva
    session.modified = True
    
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
