/**
 * Основной JavaScript файл для приложения "Электронная библиотека школьной литературы"
 */

// Ждем загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    // Инициализируем функции для разных страниц
    setupChapterPage();
    setupModalHandlers();
    setupFlashMessages();
});

/**
 * Настройка функциональности для страницы главы
 */
function setupChapterPage() {
    // Получаем элемент содержимого главы
    const chapterContent = document.querySelector('.chapter-content-text');
    if (!chapterContent) return;
    
    // Находим всех персонажей на странице
    const characters = document.querySelectorAll('.character-data');
    if (!characters.length) return;
    
    // Создаем регулярное выражение для поиска всех имен персонажей
    const characterNames = Array.from(characters).map(char => {
        return {
            id: char.dataset.id,
            name: char.dataset.name,
            regex: new RegExp(`\\b${escapeRegExp(char.dataset.name)}\\b`, 'g')
        };
    });
    
    // Получаем текст содержимого главы
    let contentHtml = chapterContent.innerHTML;
    
    // Заменяем имена персонажей на кликабельные элементы
    characterNames.forEach(char => {
        contentHtml = contentHtml.replace(char.regex, 
            `<span class="character-mention" data-character-id="${char.id}">${char.name}</span>`);
    });
    
    // Обновляем HTML
    chapterContent.innerHTML = contentHtml;
    
    // Добавляем обработчики кликов по именам персонажей
    document.querySelectorAll('.character-mention').forEach(mention => {
        mention.addEventListener('click', handleCharacterClick);
    });
}

/**
 * Обработчик клика по имени персонажа
 */
function handleCharacterClick(event) {
    const characterId = event.target.dataset.characterId;
    if (!characterId) return;
    
    // Получаем текущий URL и извлекаем ID книги и главы
    const urlParts = window.location.pathname.split('/');
    const bookId = urlParts[2];  // Предполагаем /books/{book_id}/chapter/{chapter_id}
    const chapterId = urlParts[4];
    
    // Показываем индикатор загрузки
    showLoadingModal();
    
    // Запрашиваем сводку о персонаже
    fetch(`/books/${bookId}/character/${characterId}/summary?chapter_id=${chapterId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка получения данных о персонаже');
            }
            return response.json();
        })
        .then(data => {
            // Отображаем сводку в модальном окне
            showCharacterSummary(data.summary);
        })
        .catch(error => {
            console.error('Ошибка:', error);
            showErrorModal('Не удалось загрузить информацию о персонаже');
        });
}

/**
 * Показывает модальное окно с индикатором загрузки
 */
function showLoadingModal() {
    const modal = document.getElementById('loadingModal');
    if (!modal) {
        const loadingModal = document.createElement('div');
        loadingModal.id = 'loadingModal';
        loadingModal.className = 'modal';
        loadingModal.innerHTML = `
            <div class="modal-content">
                <div class="modal-body">
                    <p>Загрузка данных о персонаже...</p>
                    <div class="loading-spinner"></div>
                </div>
            </div>
        `;
        document.body.appendChild(loadingModal);
    }
    document.getElementById('loadingModal').style.display = 'block';
}

/**
 * Показывает модальное окно с информацией о персонаже
 */
function showCharacterSummary(summary) {
    const modal = document.getElementById('summaryModal');
    if (!modal) {
        const summaryModal = document.createElement('div');
        summaryModal.id = 'summaryModal';
        summaryModal.className = 'modal';
        summaryModal.innerHTML = `
            <div class="modal-content">
                <span class="modal-close">&times;</span>
                <div class="modal-body" id="summaryContent"></div>
            </div>
        `;
        document.body.appendChild(summaryModal);
    }
    
    document.getElementById('summaryContent').innerHTML = summary;
    document.getElementById('summaryModal').style.display = 'block';
}

/**
 * Показывает модальное окно с ошибкой
 */
function showErrorModal(message) {
    const modal = document.getElementById('errorModal');
    if (!modal) {
        const errorModal = document.createElement('div');
        errorModal.id = 'errorModal';
        errorModal.className = 'modal';
        errorModal.innerHTML = `
            <div class="modal-content">
                <span class="modal-close">&times;</span>
                <div class="modal-body error-message"></div>
            </div>
        `;
        document.body.appendChild(errorModal);
    }
    
    document.querySelector('.error-message').textContent = message;
    document.getElementById('errorModal').style.display = 'block';
}

/**
 * Настройка обработчиков модальных окон
 */
function setupModalHandlers() {
    // Закрытие по клику на крестик
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-close')) {
            e.target.closest('.modal').style.display = 'none';
        }
    });
    
    // Закрытие по клику вне окна
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            e.target.style.display = 'none';
        }
    });
}

/**
 * Настройка автоматического закрытия flash-сообщений
 */
function setupFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = '0';
            setTimeout(() => flash.remove(), 500);
        }, 5000);
    });
}

/**
 * Экранирование строки для использования в регулярных выражениях
 */
function escapeRegExp(string) {
    return string.replace(/[.*+\-?^${}()|[\]\\]/g, '\\$&');
}