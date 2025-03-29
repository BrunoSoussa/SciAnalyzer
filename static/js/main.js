document.addEventListener('DOMContentLoaded', function() {
    // Elementos da interface
    const chatMessages = document.getElementById('chatMessages');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const uploadBtn = document.getElementById('uploadBtn');
    const pdfFileInput = document.getElementById('pdfFileInput');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const criteriaList = document.getElementById('criteriaList');
    const toggleCriteriaBtn = document.getElementById('toggleCriteriaBtn');
    const criteriaPanel = document.getElementById('criteriaPanel');
    const addCriteriaBtn = document.getElementById('addCriteriaBtn');
    
    // Elementos do modal de critu00e9rios
    const criteriaModal = document.getElementById('criteriaModal');
    const modalTitle = document.getElementById('modalTitle');
    const criteriaKey = document.getElementById('criteriaKey');
    const criteriaDescription = document.getElementById('criteriaDescription');
    const saveCriteriaBtn = document.getElementById('saveCriteriaBtn');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    
    // Elementos do modal de confirmau00e7u00e3o
    const confirmModal = document.getElementById('confirmModal');
    const confirmMessage = document.getElementById('confirmMessage');
    const confirmBtn = document.getElementById('confirmBtn');
    const cancelConfirmBtn = document.getElementById('cancelConfirmBtn');
    const closeConfirmBtn = document.getElementById('closeConfirmBtn');
    
    // Varu00e1veis de estado
    let currentPdfId = null;
    let currentPdfName = null;
    let isEditingCriteria = false;
    let editingCriteriaKey = null;
    let criteria = {};
    let selectedCriteria = [];
    let confirmCallback = null;
    
    // Carregar critu00e9rios do servidor
    function loadCriteria() {
        fetch('/get-criteria')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    criteria = data.criteria;
                    renderCriteriaList();
                } else {
                    console.error('Erro ao carregar critu00e9rios:', data.error);
                }
            })
            .catch(error => {
                console.error('Erro ao carregar critu00e9rios:', error);
            });
    }
    
    // Renderizar lista de critu00e9rios
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
            editBtn.title = 'Editar critu00e9rio';
            editBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                openEditCriteriaModal(key);
            });
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn-action';
            deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
            deleteBtn.title = 'Excluir critu00e9rio';
            deleteBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                showConfirmModal(
                    `Tem certeza que deseja excluir o critu00e9rio "${key}"?`,
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
    
    // Abrir modal para adicionar novo critu00e9rio
    function openAddCriteriaModal() {
        modalTitle.textContent = 'Adicionar Critu00e9rio';
        criteriaKey.value = '';
        criteriaDescription.value = '';
        criteriaKey.disabled = false;
        isEditingCriteria = false;
        editingCriteriaKey = null;
        criteriaModal.style.display = 'flex';
    }
    
    // Abrir modal para editar critu00e9rio existente
    function openEditCriteriaModal(key) {
        modalTitle.textContent = 'Editar Critu00e9rio';
        criteriaKey.value = key;
        criteriaDescription.value = criteria[key];
        criteriaKey.disabled = true;
        isEditingCriteria = true;
        editingCriteriaKey = key;
        criteriaModal.style.display = 'flex';
    }
    
    // Fechar modal de critu00e9rios
    function closeCriteriaModal() {
        criteriaModal.style.display = 'none';
    }
    
    // Salvar critu00e9rio (novo ou editado)
    function saveCriteria() {
        const key = criteriaKey.value.trim();
        const description = criteriaDescription.value.trim();
        
        if (!key) {
            alert('O identificador do critu00e9rio u00e9 obrigatu00f3rio');
            return;
        }
        
        if (!description) {
            alert('A descriu00e7u00e3o do critu00e9rio u00e9 obrigatu00f3ria');
            return;
        }
        
        // Validar formato do identificador (apenas letras minu00fasculas, nu00fameros e underscores)
        if (!/^[a-z0-9_]+$/.test(key)) {
            alert('O identificador deve conter apenas letras minu00fasculas, nu00fameros e underscores');
            return;
        }
        
        // Se nu00e3o estiver editando e a chave ju00e1 existir
        if (!isEditingCriteria && criteria[key]) {
            alert(`O critu00e9rio "${key}" ju00e1 existe. Escolha outro identificador.`);
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
                alert(`Erro ao salvar critu00e9rio: ${data.error}`);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Erro ao salvar critu00e9rio:', error);
            alert('Ocorreu um erro ao salvar o critu00e9rio. Tente novamente.');
        });
    }
    
    // Excluir critu00e9rio
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
                alert(`Erro ao excluir critu00e9rio: ${data.error}`);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Erro ao excluir critu00e9rio:', error);
            alert('Ocorreu um erro ao excluir o critu00e9rio. Tente novamente.');
        });
    }
    
    // Mostrar modal de confirmau00e7u00e3o
    function showConfirmModal(message, callback) {
        confirmMessage.textContent = message;
        confirmCallback = callback;
        confirmModal.style.display = 'flex';
    }
    
    // Fechar modal de confirmau00e7u00e3o
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
            // Substituir links por elementos <a>
            content = content.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
            
            // Substituir **texto** por <strong>texto</strong>
            content = content.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
            
            // Substituir *texto* por <em>texto</em>
            content = content.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
            
            // Substituir `texto` por <code>texto</code>
            content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
            
            // Substituir blocos de cu00f3digo
            content = content.replace(/```([\s\S]+?)```/g, '<pre><code>$1</code></pre>');
            
            // Substituir quebras de linha por <br>
            content = content.replace(/\n/g, '<br>');
        }
        
        messageDiv.innerHTML = `
            <div class="message-content">${content}</div>
        `;
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Enviar mensagem para o chat
    function sendMessage() {
        const message = messageInput.value.trim();
        
        if (!message) {
            return;
        }
        
        if (!currentPdfId) {
            addMessage('system', 'Por favor, fau00e7a upload de um PDF antes de enviar uma mensagem.', true);
            return;
        }
        
        // Adicionar mensagem do usuu00e1rio ao chat
        addMessage('user', message);
        
        // Limpar campo de entrada
        messageInput.value = '';
        
        // Mostrar indicador de carregamento
        showLoading();
        
        // Obter critu00e9rios selecionados
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
                criteria: criteriaToSend
            })
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            
            if (data.success) {
                addMessage('system', data.response);
            } else {
                addMessage('system', `Erro: ${data.error}`, true);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Erro ao enviar mensagem:', error);
            addMessage('system', 'Ocorreu um erro ao processar sua mensagem. Tente novamente.', true);
        });
    }
    
    // Fazer upload de PDF
    function uploadPdf() {
        const file = pdfFileInput.files[0];
        
        if (!file) {
            return;
        }
        
        if (file.type !== 'application/pdf') {
            addMessage('system', 'Por favor, selecione um arquivo PDF vu00e1lido.', true);
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
                addMessage('system', `PDF "${file.name}" carregado com sucesso. Agora vocu00ea pode fazer perguntas sobre o conteu00fado.`);
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
    
    // Alternar visibilidade do painel de critu00e9rios
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
