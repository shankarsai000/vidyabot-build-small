/**
 * Main VidyaBot App
 * Orchestrates all functionality
 */

class VidyaBotApp {
  constructor() {
    this.currentTextbookId = null;
    this.init();
  }

  async init() {
    console.log('🚀 VidyaBot initializing...');
    
    try {
      // Check API health
      const health = await API.health();
      console.log('✅ API healthy:', health);
      
      // Load textbooks
      await this.loadTextbooks();
      
      // Setup event listeners
      this.setupListeners();
      
      // Load statistics
      await this.updateDashboard();
      
      console.log('✅ VidyaBot ready!');
    } catch (error) {
      console.error('Initialization error:', error);
      UI.showError('Failed to load app. Please refresh the page.');
    }
  }

  // Load textbooks from API
  async loadTextbooks() {
    try {
      const response = await API.getTextbooks();
      
      if (response.status !== 'success' || !response.textbooks) {
        console.warn('No textbooks loaded');
        return;
      }
      
      const textbooks = response.textbooks;
      const select = document.getElementById('textbook-select');
      
      // Populate dropdown
      select.innerHTML = '<option value="">Select a Textbook</option>';
      
      textbooks.forEach(textbook => {
        const option = document.createElement('option');
        option.value = textbook.id;
        option.textContent = `${textbook.title} (${textbook.board} - Grade ${textbook.grade})`;
        select.appendChild(option);
      });
      
      if (textbooks.length > 0) {
        select.value = textbooks[0].id;
        this.currentTextbookId = textbooks[0].id;
      }
      
      console.log(`✅ Loaded ${textbooks.length} textbooks`);
    } catch (error) {
      console.error('Error loading textbooks:', error);
    }
  }

  // Setup event listeners
  setupListeners() {
    // Question input and button
    const askButton = document.getElementById('ask-button');
    const questionInput = document.getElementById('question-input');
    const textbookSelect = document.getElementById('textbook-select');
    
    if (askButton) {
      askButton.addEventListener('click', () => this.handleAskQuestion());
    }
    
    if (questionInput) {
      questionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
          this.handleAskQuestion();
        }
      });
    }

    if (textbookSelect) {
      textbookSelect.addEventListener('change', (e) => {
        this.currentTextbookId = parseInt(e.target.value);
      });
    }

    // Ask Again button
    const askAgainBtn = document.getElementById('ask-again-button');
    if (askAgainBtn) {
      askAgainBtn.addEventListener('click', () => {
        UI.hideAnswer();
        document.getElementById('question-input').focus();
      });
    }

    // Upload handlers
    const uploadZone = document.getElementById('upload-zone');
    const pdfInput = document.getElementById('pdf-input');
    const uploadForm = document.getElementById('upload-form');
    
    if (uploadZone && pdfInput) {
      // Click to select
      uploadZone.addEventListener('click', () => pdfInput.click());
      
      // Drag and drop
      uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
      });
      
      uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
      });
      
      uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
          pdfInput.files = files;
          this.handlePDFSelected(files[0]);
        }
      });
      
      pdfInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          this.handlePDFSelected(e.target.files[0]);
        }
      });
    }

    if (uploadForm) {
      uploadForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.handleUploadSubmit();
      });
    }
  }

  // Handle ask question button click
  async handleAskQuestion() {
    const question = document.getElementById('question-input').value.trim();
    const textbookId = this.currentTextbookId;
    const language = document.getElementById('language-select').value;
    const mode = document.getElementById('mode-select').value;

    if (!question) {
      UI.showError('Please ask a question first!');
      return;
    }

    if (!textbookId) {
      UI.showError('Please select a textbook!');
      return;
    }

    try {
      UI.hideError();
      UI.showLoading(true);
      UI.setButtonLoading('ask-button', true);

      const response = await API.query(question, textbookId, language, mode);

      UI.showLoading(false);
      UI.setButtonLoading('ask-button', false);

      if (!response || response.status === 'error') {
        throw new Error(response?.detail || 'Failed to get answer');
      }

      // Clear input
      document.getElementById('question-input').value = '';
      document.getElementById('char-count').textContent = '0';

      // Display answer
      UI.displayAnswer(response);

      // Update dashboard
      await this.updateDashboard();

    } catch (error) {
      console.error('Query error:', error);
      UI.showLoading(false);
      UI.setButtonLoading('ask-button', false);
      UI.showError(error.message || 'Failed to get answer. Check your connection.');
    }
  }

  // Handle PDF file selection
  handlePDFSelected(file) {
    console.log('PDF selected:', file.name);
    
    // Validate file
    if (file.type !== 'application/pdf') {
      UI.showError('Please select a PDF file!');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      UI.showError('File is too large (max 50MB)');
      return;
    }
  }

  // Handle upload form submit
  async handleUploadSubmit() {
    const pdfInput = document.getElementById('pdf-input');
    const bookTitle = document.getElementById('book-title').value.trim();
    const board = document.getElementById('board').value;
    const subject = document.getElementById('subject').value.trim();
    const grade = document.getElementById('grade').value.trim();

    if (!pdfInput.files || pdfInput.files.length === 0) {
      UI.showError('Please select a PDF file!');
      return;
    }

    if (!board) {
      UI.showError('Please select a board!');
      return;
    }

    try {
      UI.showUploadProgress(true);
      UI.setButtonLoading('upload-button', true);

      const file = pdfInput.files[0];

      const response = await API.uploadPDF(
        file,
        board,
        subject,
        grade,
        bookTitle,
        (percent) => UI.updateProgress(percent)
      );

      if (response.status !== 'success') {
        throw new Error(response.message || 'Upload failed');
      }

      // Success
      UI.showUploadProgress(false);
      UI.setButtonLoading('upload-button', false);

      const message = `✅ Added "${response.title}" with ${response.total_chunks} chunks!`;
      UI.showSuccess(message);

      // Clear form
      UI.clearForm('upload-form');

      // Reload textbooks
      await this.loadTextbooks();

      // Reset to home screen after 3 seconds
      setTimeout(() => {
        UI.switchTab('home');
      }, 3000);

    } catch (error) {
      console.error('Upload error:', error);
      UI.showUploadProgress(false);
      UI.setButtonLoading('upload-button', false);
      UI.showError(error.message || 'Upload failed');
    }
  }

  // Update dashboard
  async updateDashboard() {
    try {
      const stats = await API.getStats();
      
      if (!stats || stats.total_queries === undefined) {
        console.warn('Invalid stats received');
        return;
      }

      // Update stat cards
      document.getElementById('stat-queries').textContent = UI.formatNumber(stats.total_queries);
      document.getElementById('stat-cache-hit').textContent = 
        (stats.cache_hit_rate * 100).toFixed(1) + '%';
      document.getElementById('stat-tokens-saved').textContent = 
        UI.formatNumber(stats.total_tokens_saved);
      document.getElementById('stat-cost').textContent = 
        '$' + stats.total_cost_usd.toFixed(4);

      // Update savings banner
      const savingsUSD = stats.total_savings_usd || 0;
      const savingsINR = (savingsUSD * 75).toFixed(2);
      document.getElementById('savings-title').textContent = 
        `💰 You've Saved ₹${savingsINR} in API Costs!`;

      // UPDATE LIVE SAVINGS METER - Judge Impact Feature
      this.updateSavingsMeter(stats);

      // Update chart
      if (stats.avg_tokens_per_query) {
        const chartActual = (stats.avg_tokens_per_query / stats.baseline_tokens) * 100;
        document.getElementById('chart-actual').style.height = Math.max(10, chartActual) + '%';
        document.getElementById('chart-actual-value').textContent = 
          Math.round(stats.avg_tokens_per_query || 0);
      }
      
      document.getElementById('chart-baseline-value').textContent = 
        stats.baseline_tokens;
      document.getElementById('chart-baseline').style.height = '100%';

      // Load recent queries
      if (stats.total_queries > 0) {
        await this.loadRecentQueries();
      }

    } catch (error) {
      console.error('Error updating dashboard:', error);
    }
  }

  // Update live savings meter with extrapolation to 1,000 students
  updateSavingsMeter(stats) {
    try {
      // Calculate session metrics
      const avgTokensActual = stats.avg_tokens_per_query || 245;  // v2 elite: 245
      const baselineTokens = stats.baseline_tokens || 2000;
      const reductionPct = Math.round(((baselineTokens - avgTokensActual) / baselineTokens) * 100);
      const tokensSaved = baselineTokens - avgTokensActual;

      // Update session bar
      const reductionBar = document.getElementById('session-reduction-bar');
      if (reductionBar) {
        reductionBar.style.width = reductionPct + '%';
        reductionBar.querySelector('.progress-text').textContent = reductionPct + '% Pruned';
      }

      // Update session stats
      document.getElementById('session-tokens-actual').textContent = Math.round(avgTokensActual);
      document.getElementById('session-tokens-saved').textContent = UI.formatNumber(Math.round(tokensSaved));

      // Calculate scale to 1,000 students
      const pricePerToken = 0.25 / 1_000_000;  // Haiku: $0.25 per 1M tokens
      const costPerQuery = avgTokensActual * pricePerToken;
      const savingsPerQuery = (baselineTokens * pricePerToken) - costPerQuery;
      
      // INR conversion (1 USD = 75 INR)
      const savingsPerQueryINR = savingsPerQuery * 75;
      const savingsPerStudentPerDay = savingsPerQueryINR * 10;  // 10 queries/day
      const savingsPer1000StudentsPerDay = savingsPerStudentPerDay * 1000;
      const savingsPer1000StudentsPerMonth = savingsPer1000StudentsPerDay * 30;

      // Update breakdown items
      const items = document.querySelectorAll('.breakdown-item');
      if (items.length >= 3) {
        // Per student per day
        const item1Values = items[0].querySelectorAll('[class$="-value"]');
        if (item1Values.length > 0) {
          item1Values[item1Values.length - 1].textContent = '₹' + savingsPerStudentPerDay.toFixed(2);
        }

        // Daily savings (1,000 students)
        const item2Values = items[1].querySelectorAll('[class$="-value"]');
        if (item2Values.length > 0) {
          item2Values[item2Values.length - 1].textContent = '₹' + Math.round(savingsPer1000StudentsPerDay);
        }

        // Monthly savings (1,000 students) - HIGHLIGHT
        const item3Values = items[2].querySelectorAll('[class$="-value"]');
        if (item3Values.length > 0) {
          item3Values[item3Values.length - 1].textContent = '₹' + Math.round(savingsPer1000StudentsPerMonth).toLocaleString() + ' 🇮🇳';
        }
      }

      // Animate the updates
      const meter = document.querySelector('.savings-meter');
      if (meter && stats.total_queries > 0) {
        meter.style.animation = 'pulse 0.5s ease';
        setTimeout(() => {
          meter.style.animation = 'none';
        }, 500);
      }

    } catch (error) {
      console.error('Error updating savings meter:', error);
    }
  }

  // Load recent queries table
  async loadRecentQueries() {
    try {
      const response = await API.getRecentQueries(5);
      
      if (!response.queries || response.queries.length === 0) {
        return;
      }

      const tbody = document.getElementById('recent-queries');
      tbody.innerHTML = '';

      response.queries.forEach(query => {
        const row = tbody.insertRow();
        row.innerHTML = `
          <td>${UI.formatDate(query.timestamp)}</td>
          <td>${UI.formatNumber(query.actual_tokens_used)}</td>
          <td>₹${(query.cost_saved_usd * 75).toFixed(2)}</td>
          <td>${query.cache_hit ? '✅ Cache' : '📚 Textbook'}</td>
        `;
      });

    } catch (error) {
      console.error('Error loading recent queries:', error);
    }
  }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.app = new VidyaBotApp();
});
