# Flask API com Gemini para Análise de PDFs

Esta API permite fazer upload de arquivos PDF e usar o modelo Gemini da Google para responder perguntas sobre o conteúdo dos documentos.

## Funcionalidades

- Upload de arquivos PDF
- Extração de texto dos PDFs
- Análise do conteúdo usando o Gemini Pro
- Interface web simples para testar a API
- Endpoints RESTful para integração com outros sistemas

## Requisitos

- Python 3.8+
- Dependências listadas em `requirements.txt`

## Instalação

1. Clone o repositório ou baixe os arquivos
2. Instale as dependências:

```bash
pip install -r requirements.txt
```

## Uso

### Iniciar o servidor

```bash
python app.py
```

O servidor estará disponível em http://localhost:5000

### Endpoints da API

#### 1. Interface Web
- **URL**: `/`
- **Método**: GET
- **Descrição**: Interface web para testar o upload de PDFs e fazer perguntas

#### 2. Verificação de Saúde
- **URL**: `/health`
- **Método**: GET
- **Descrição**: Verifica se a API está funcionando

#### 3. Análise de PDF
- **URL**: `/analyze-pdf`
- **Método**: POST
- **Parâmetros**:
  - `file`: Arquivo PDF (multipart/form-data)
  - `question`: Pergunta sobre o PDF (opcional)
- **Resposta**: JSON com a resposta do Gemini

#### 4. Fazer Perguntas Diretamente
- **URL**: `/ask`
- **Método**: POST
- **Corpo**: JSON
  ```json
  {
    "question": "Sua pergunta aqui",
    "context": "Contexto ou texto para análise"
  }
  ```
- **Resposta**: JSON com a resposta do Gemini

## Observações

- A API usa a chave do Gemini fornecida no código
- Há um limite de tamanho para o texto extraído do PDF (aproximadamente 30.000 tokens)
- Para arquivos muito grandes, o conteúdo será truncado
