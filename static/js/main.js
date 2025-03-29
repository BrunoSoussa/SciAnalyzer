document.addEventListener('DOMContentLoaded', function() {
    // Elementos da interface
    const chatMessages = document.getElementById('chatMessages');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const uploadBtn = document.getElementById('uploadBtn');
    const pdfFileInput = document.getElementById('pdfFileInput');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const criteriaList = document.getElementById('criteriaList');
    const toggleCriteriaBtn = document.getElementById('toggleCriteriaBtn');
    const criteriaPanel = document.getElementById('criteriaPanel');
    const addCriteriaBtn = document.getElementById('addCriteriaBtn');
    
    // Elementos do modal de critérios
    const criteriaModal = document.getElementById('criteriaModal');
    const modalTitle = document.getElementById('modalTitle');
    const criteriaKey = document.getElementById('criteriaKey');
    const criteriaDescription = document.getElementById('criteriaDescription');
    const saveCriteriaBtn = document.getElementById('saveCriteriaBtn');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    
    // Elementos do modal de confirmação
    const confirmModal = document.getElementById('confirmModal');
    const confirmMessage = document.getElementById('confirmMessage');
    const confirmBtn = document.getElementById('confirmBtn');
    const cancelConfirmBtn = document.getElementById('cancelConfirmBtn');
    const closeConfirmBtn = document.getElementById('closeConfirmBtn');
    
    // Variáveis de estado
    let currentPdfId = null;
    let currentPdfName = null;
    let isEditingCriteria = false;
    let editingCriteriaKey = null;
    let criteria = {};
    let selectedCriteria = [];
    let confirmCallback = null;
    
    // Carregar critérios do servidor
    function loadCriteria() {
        fetch('/get-criteria')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    criteria = data.criteria;
                    renderCriteriaList();
                } else {
                    console.error('Erro ao carregar critérios:', data.error);
                }
            })
            .catch(error => {
                console.error('Erro ao carregar critérios:', error);
            });
    }
    
    // Renderizar lista de critérios
    function renderCriteriaList() {
        criteriaList.innerHTML = '';
        
        Object.keys(criteria).forEach(key => {
            const criteriaItem = document.createElement('div');
            criteriaItem.className = 'criteria-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `criteria-${key}`;
            checkbox.checked = selectedCriteria.includes(key);
            checkbox.addEventListener('change', function() {
                if (this.checked) {
                    if (!selectedCriteria.includes(key)) {
                        selectedCriteria.push(key);
                    }
                } else {
                    selectedCriteria = selectedCriteria.filter(k => k !== key);
                }
            });
            
            const label = document.createElement('label');
            label.className = 'criteria-label';
            label.htmlFor = `criteria-${key}`;
            label.title = criteria[key];
            label.textContent = key;
            
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'criteria-actions';
            
            const editBtn = document.createElement('button');
            editBtn.className = 'btn-action';
            editBtn.innerHTML = '<i class="fas fa-edit"></i>';
            editBtn.title = 'Editar critério';
            editBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                openEditCriteriaModal(key);
            });
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn-action';
            deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
            deleteBtn.title = 'Excluir critério';
            deleteBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                showConfirmModal(
                    `Tem certeza que deseja excluir o critério "${key}"?`,
                    () => deleteCriteria(key)
                );
            });
            
            actionsDiv.appendChild(editBtn);
            actionsDiv.appendChild(deleteBtn);
            
            criteriaItem.appendChild(checkbox);
            criteriaItem.appendChild(label);
            criteriaItem.appendChild(actionsDiv);
            
            criteriaList.appendChild(criteriaItem);
        });
    }
    
    // Abrir modal para adicionar novo critério
    function openAddCriteriaModal() {
        modalTitle.textContent = 'Adicionar Critério';
        criteriaKey.value = '';
        criteriaDescription.value = '';
        criteriaKey.disabled = false;
        isEditingCriteria = false;
        editingCriteriaKey = null;
        criteriaModal.style.display = 'flex';
    }
    
    // Abrir modal para editar critério existente
    function openEditCriteriaModal(key) {
        modalTitle.textContent = 'Editar Critério';
        criteriaKey.value = key;
        criteriaDescription.value = criteria[key];
        criteriaKey.disabled = true;
        isEditingCriteria = true;
        editingCriteriaKey = key;
        criteriaModal.style.display = 'flex';
    }
    
    // Fechar modal de critérios
    function closeCriteriaModal() {
        criteriaModal.style.display = 'none';
    }
    
    // Salvar critério (novo ou editado)
    function saveCriteria() {
        const key = criteriaKey.value.trim();
        const description = criteriaDescription.value.trim();
        
        if (!key) {
            alert('O identificador do critério é obrigatório');
            return;
        }
        
        if (!description) {
            alert('A descrição do critério é obrigatória');
            return;
        }
        
        // Validar formato do identificador (apenas letras minúsculas, números e underscores)
        if (!/^[a-z0-9_]+$/.test(key)) {
            alert('O identificador deve conter apenas letras minúsculas, números e underscores');
            return;
        }
        
        // Se não estiver editando e a chave já existir
        if (!isEditingCriteria && criteria[key]) {
            alert(`O critério "${key}" já existe. Escolha outro identificador.`);
            return;
        }
        
        showLoading();
        
        fetch('/save-criteria', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                key: key,
                description: description
            })
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.success) {
                criteria[key] = description;
                renderCriteriaList();
                closeCriteriaModal();
            } else {
                alert(`Erro ao salvar critério: ${data.error}`);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Erro ao salvar critério:', error);
            alert('Ocorreu um erro ao salvar o critério. Tente novamente.');
        });
    }
    
    // Excluir critério
    function deleteCriteria(key) {
        showLoading();
        
        fetch('/delete-criteria', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ key: key })
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.success) {
                delete criteria[key];
                selectedCriteria = selectedCriteria.filter(k => k !== key);
                renderCriteriaList();
            } else {
                alert(`Erro ao excluir critério: ${data.error}`);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Erro ao excluir critério:', error);
            alert('Ocorreu um erro ao excluir o critério. Tente novamente.');
        });
    }
    
    // Mostrar modal de confirmação
    function showConfirmModal(message, callback) {
        confirmMessage.textContent = message;
        confirmCallback = callback;
        confirmModal.style.display = 'flex';
    }
    
    // Fechar modal de confirmação
    function closeConfirmModal() {
        confirmModal.style.display = 'none';
        confirmCallback = null;
    }
    
    // Exibir overlay de carregamento
    function showLoading() {
        loadingOverlay.style.display = 'flex';
    }
    
    // Ocultar overlay de carregamento
    function hideLoading() {
        loadingOverlay.style.display = 'none';
    }
    
    // Adicionar mensagem ao chat
    function addMessage(sender, content, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        if (isError) {
            messageDiv.classList.add('error-message');
        }
        
        // Converter markdown para HTML se for mensagem do sistema
        if (sender === 'system') {
            content = formatMarkdown(content);
        }
        
        messageDiv.innerHTML = `
            <div class="message-content">${content}</div>
        `;
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Formatar markdown para HTML
    function formatMarkdown(text) {
        // Preservar blocos de código antes de outras transformações
        const codeBlocks = [];
        text = text.replace(/```([\s\S]+?)```/g, function(match) {
            codeBlocks.push(match);
            return "%%CODEBLOCK_" + (codeBlocks.length - 1) + "%%";
        });
        
        // Preservar código inline
        const inlineCode = [];
        text = text.replace(/`([^`]+)`/g, function(match) {
            inlineCode.push(match);
            return "%%INLINECODE_" + (inlineCode.length - 1) + "%%";
        });
        
        // Substituir links por elementos <a>
        text = text.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        
        // Formatar títulos
        text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        
        // Substituir **texto** por <strong>texto</strong>
        text = text.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
        
        // Substituir *texto* por <em>texto</em>
        text = text.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
        
        // Formatar listas não ordenadas
        text = text.replace(/^\* (.+)$/gm, '<li>$1</li>');
        text = text.replace(/^- (.+)$/gm, '<li>$1</li>');
        
        // Formatar listas ordenadas
        text = text.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
        
        // Agrupar itens de lista
        text = text.replace(/(<li>.+<\/li>\s*)+/g, '<ul>$&</ul>');
        
        // Formatar tabelas (formato markdown simplificado)
        let tableMatch = text.match(/\|(.+)\|\s*\n\|\s*[-:\|\s]+\|\s*\n((\|.+\|\s*\n)+)/g);
        if (tableMatch) {
            tableMatch.forEach(table => {
                let rows = table.split('\n').filter(row => row.trim() !== '');
                let headers = rows[0].split('|').filter(cell => cell.trim() !== '').map(cell => cell.trim());
                let htmlTable = '<table><thead><tr>';
                
                // Headers
                headers.forEach(header => {
                    htmlTable += `<th>${header}</th>`;
                });
                htmlTable += '</tr></thead><tbody>';
                
                // Rows (skip header and separator rows)
                for (let i = 2; i < rows.length; i++) {
                    let cells = rows[i].split('|').filter(cell => cell.trim() !== '').map(cell => cell.trim());
                    htmlTable += '<tr>';
                    cells.forEach(cell => {
                        htmlTable += `<td>${cell}</td>`;
                    });
                    htmlTable += '</tr>';
                }
                
                htmlTable += '</tbody></table>';
                text = text.replace(table, htmlTable);
            });
        }
        
        // Formatar citações
        text = text.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
        
        // Substituir quebras de linha por <br>
        text = text.replace(/\n/g, '<br>');
        
        // Restaurar blocos de código
        for (let i = 0; i < codeBlocks.length; i++) {
            let code = codeBlocks[i].replace(/```([\s\S]+?)```/g, '$1').trim();
            text = text.replace("%%CODEBLOCK_" + i + "%%", `<pre><code>${code}</code></pre>`);
        }
        
        // Restaurar código inline
        for (let i = 0; i < inlineCode.length; i++) {
            let code = inlineCode[i].replace(/`([^`]+)`/g, '$1');
            text = text.replace("%%INLINECODE_" + i + "%%", `<code>${code}</code>`);
        }
        
        return text;
    }
    
    // Adicionar indicador de digitação
    function addTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message system-message typing-indicator';
        typingDiv.id = 'typingIndicator';
        
        typingDiv.innerHTML = `
            <div class="typing-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;
        
        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Remover indicador de digitação
    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    // Enviar mensagem para o chat
    function sendMessage() {
        const message = messageInput.value.trim();
        
        if (!message) {
            return;
        }
        
        if (!currentPdfId) {
            addMessage('system', 'Por favor, faça upload de um PDF antes de enviar uma mensagem.', true);
            return;
        }
        
        // Adicionar mensagem do usuário ao chat
        addMessage('user', message);
        
        // Limpar campo de entrada
        messageInput.value = '';
        
        // Mostrar indicador de digitação
        addTypingIndicator();
        
        // Obter critérios selecionados
        const criteriaToSend = {};
        selectedCriteria.forEach(key => {
            criteriaToSend[key] = criteria[key];
        });
        
        // Enviar mensagem para o servidor
        fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                pdf_id: currentPdfId,
                criteria: criteriaToSend,
                is_analysis: false
            })
        })
        .then(response => response.json())
        .then(data => {
            // Remover indicador de digitação
            removeTypingIndicator();
            
            if (data.success) {
                addMessage('system', data.response);
            } else {
                addMessage('system', `Erro: ${data.error}`, true);
            }
        })
        .catch(error => {
            // Remover indicador de digitação
            removeTypingIndicator();
            
            console.error('Erro ao enviar mensagem:', error);
            addMessage('system', 'Ocorreu um erro ao processar sua mensagem. Tente novamente.', true);
        });
    }
    
    // Gerar análise completa
    function generateAnalysis() {
        if (!currentPdfId) {
            addMessage('system', 'Por favor, faça upload de um PDF antes de gerar uma análise.', true);
            return;
        }
        
        // Adicionar mensagem do usuário ao chat
        addMessage('user', 'Gerar análise completa do documento');
        
        // Mostrar indicador de digitação
        addTypingIndicator();
        
        // Obter critérios selecionados
        const criteriaToSend = {};
        selectedCriteria.forEach(key => {
            criteriaToSend[key] = criteria[key];
        });
        
        // Se não houver critérios selecionados, usar todos os critérios disponíveis
        if (Object.keys(criteriaToSend).length === 0) {
            Object.keys(criteria).forEach(key => {
                criteriaToSend[key] = criteria[key];
            });
        }
        
        console.log('Enviando solicitação de análise com os seguintes critérios:', criteriaToSend);
        console.log('PDF ID:', currentPdfId);
        
        // Enviar solicitação de análise para o servidor
        fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: 'Faça uma análise completa deste artigo.',
                pdf_id: currentPdfId,
                criteria: criteriaToSend,
                is_analysis: true
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Erro HTTP: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Remover indicador de digitação
            removeTypingIndicator();
            
            if (data.success) {
                addMessage('system', data.response);
            } else {
                console.error('Erro na resposta do servidor:', data.error);
                addMessage('system', `Erro: ${data.error}`, true);
            }
        })
        .catch(error => {
            // Remover indicador de digitação
            removeTypingIndicator();
            
            console.error('Erro ao gerar análise:', error);
            addMessage('system', 'Ocorreu um erro ao gerar a análise. Tente novamente.', true);
        });
    }
    
    // Fazer upload de PDF
    function uploadPdf() {
        const file = pdfFileInput.files[0];
        
        if (!file) {
            return;
        }
        
        if (file.type !== 'application/pdf') {
            addMessage('system', 'Por favor, selecione um arquivo PDF válido.', true);
            return;
        }
        
        // Criar FormData
        const formData = new FormData();
        formData.append('pdf', file);
        
        // Mostrar indicador de carregamento
        showLoading();
        
        // Enviar arquivo para o servidor
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            
            if (data.success) {
                currentPdfId = data.pdf_id;
                currentPdfName = file.name;
                addMessage('system', `PDF "${file.name}" carregado com sucesso. Agora você pode fazer perguntas sobre o conteúdo.`);
            } else {
                addMessage('system', `Erro ao carregar PDF: ${data.error}`, true);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Erro ao fazer upload:', error);
            addMessage('system', 'Ocorreu um erro ao fazer upload do PDF. Tente novamente.', true);
        });
    }
    
    // Alternar visibilidade do painel de critérios
    function toggleCriteriaPanel() {
        const content = criteriaPanel.querySelector('.criteria-content');
        const icon = toggleCriteriaBtn.querySelector('i');
        
        if (content.style.display === 'none') {
            content.style.display = 'block';
            icon.className = 'fas fa-chevron-up';
        } else {
            content.style.display = 'none';
            icon.className = 'fas fa-chevron-down';
        }
    }
    
    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    
    analyzeBtn.addEventListener('click', generateAnalysis);
    
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    uploadBtn.addEventListener('click', function() {
        pdfFileInput.click();
    });
    
    pdfFileInput.addEventListener('change', uploadPdf);
    
    toggleCriteriaBtn.addEventListener('click', toggleCriteriaPanel);
    
    addCriteriaBtn.addEventListener('click', openAddCriteriaModal);
    
    closeModalBtn.addEventListener('click', closeCriteriaModal);
    cancelEditBtn.addEventListener('click', closeCriteriaModal);
    saveCriteriaBtn.addEventListener('click', saveCriteria);
    
    confirmBtn.addEventListener('click', function() {
        if (confirmCallback) {
            confirmCallback();
        }
        closeConfirmModal();
    });
    
    cancelConfirmBtn.addEventListener('click', closeConfirmModal);
    closeConfirmBtn.addEventListener('click', closeConfirmModal);
    
    // Inicializar
    loadCriteria();
});
