/**
 * UI Helper Functions
 * DOM manipulation, screen switching, event handling
 */

const UI = {
  // Switch between screens/tabs
  switchTab(tabName) {
    // Hide all screens
    document.querySelectorAll('.screen').forEach(screen => {
      screen.classList.remove('active');
    });
    
    // Remove active class from nav tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.classList.remove('active');
    });
    
    // Show selected screen
    const screen = document.getElementById(tabName);
    if (screen) {
      screen.classList.add('active');
    }
    
    // Mark nav tab as active
    const navTab = document.querySelector(`[data-tab="${tabName}"]`);
    if (navTab) {
      navTab.classList.add('active');
    }
  },

  // Show loading indicator
  showLoading(show = true) {
    const loading = document.getElementById('loading-indicator');
    if (show) {
      loading.classList.remove('hidden');
    } else {
      loading.classList.add('hidden');
    }
  },

  // Show error message
  showError(message) {
    const errorEl = document.getElementById('error-message');
    errorEl.textContent = '❌ ' + message;
    errorEl.classList.remove('hidden');
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
      errorEl.classList.add('hidden');
    }, 5000);
  },

  // Hide error message
  hideError() {
    document.getElementById('error-message').classList.add('hidden');
  },

  // Display answer
  displayAnswer(data) {
    const container = document.getElementById('answer-container');
    const answerText = document.getElementById('answer-text');
    const sourceInfo = document.getElementById('source-info');
    const costBadge = document.getElementById('cost-badge-text');
    
    answerText.textContent = data.answer;
    
    // Source citation
    if (data.source_pages) {
      sourceInfo.innerHTML = `<strong>Source:</strong> Chapter ${data.source_pages}`;
    } else {
      sourceInfo.innerHTML = '<strong>Source:</strong> Your textbook';
    }
    
    // Cost savings badge
    const savings = ((data.tokens_saved / data.baseline_tokens) * 100).toFixed(1);
    costBadge.innerHTML = `
      💰 Saved ${savings}% • ₹${(data.cost_saved_usd * 75).toFixed(2)} used
      <br>
      <small>${data.tokens_used} tokens (baseline: ${data.baseline_tokens})</small>
    `;
    
    container.classList.remove('hidden');
    
    // Scroll to answer
    setTimeout(() => {
      container.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  },

  // Hide answer
  hideAnswer() {
    document.getElementById('answer-container').classList.add('hidden');
  },

  // Update button state
  setButtonLoading(buttonId, isLoading = true) {
    const btn = document.getElementById(buttonId);
    if (isLoading) {
      btn.disabled = true;
      btn.querySelector('.btn-text').classList.add('hidden');
      btn.querySelector('.btn-spinner').classList.remove('hidden');
    } else {
      btn.disabled = false;
      btn.querySelector('.btn-text').classList.remove('hidden');
      btn.querySelector('.btn-spinner').classList.add('hidden');
    }
  },

  // Update progress bar
  updateProgress(percent) {
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');
    fill.style.width = percent + '%';
    text.textContent = `Processing: ${Math.round(percent)}%`;
  },

  // Format number with comma separators
  formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  },

  // Format currency
  formatCurrency(amount) {
    return '₹' + amount.toFixed(2);
  },

  // Format date
  formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  },

  // Show/hide offline banner
  updateOnlineStatus() {
    const banner = document.getElementById('offline-banner');
    if (navigator.onLine) {
      banner.classList.add('hidden');
    } else {
      banner.classList.remove('hidden');
    }
  },

  // Populate dropdown
  populateDropdown(selectId, items, valueKey = 'id', labelKey = 'title') {
    const select = document.getElementById(selectId);
    select.innerHTML = '<option value="">Select an option</option>';
    
    items.forEach(item => {
      const option = document.createElement('option');
      option.value = item[valueKey];
      option.textContent = item[labelKey];
      select.appendChild(option);
    });
  },

  // Copy text to clipboard
  copyToClipboard(text) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        // Show success message
        const btn = document.getElementById('copy-answer-button');
        const originalText = btn.textContent;
        btn.textContent = '✓ Copied!';
        setTimeout(() => {
          btn.textContent = originalText;
        }, 2000);
      });
    } else {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
  },

  // Clear form
  clearForm(formId) {
    const form = document.getElementById(formId);
    if (form) {
      form.reset();
      // Reset file input separately (some browsers don't clear it with reset())
      const fileInput = form.querySelector('input[type="file"]');
      if (fileInput) {
        fileInput.value = '';
      }
    }
  },

  // Show upload progress
  showUploadProgress(show = true) {
    const progress = document.getElementById('upload-progress');
    if (show) {
      progress.classList.remove('hidden');
    } else {
      progress.classList.add('hidden');
    }
  },

  // Show success message
  showSuccess(message) {
    const successContainer = document.getElementById('upload-success');
    const messageText = document.getElementById('success-message-text');
    messageText.textContent = message;
    successContainer.classList.remove('hidden');
    
    // Auto-hide after 8 seconds
    setTimeout(() => {
      successContainer.classList.add('hidden');
    }, 8000);
  }
};

// Setup event delegation for dynamic content
document.addEventListener('DOMContentLoaded', () => {
  // Character counter for question input
  const questionInput = document.getElementById('question-input');
  const charCount = document.getElementById('char-count');
  
  if (questionInput && charCount) {
    questionInput.addEventListener('input', () => {
      charCount.textContent = questionInput.value.length;
    });
  }

  // Online/offline detection
  window.addEventListener('online', () => UI.updateOnlineStatus());
  window.addEventListener('offline', () => UI.updateOnlineStatus());
  
  UI.updateOnlineStatus();

  // Navigation tabs
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.getAttribute('data-tab');
      UI.switchTab(tabName);
    });
  });

  // Close answer button
  const closeAnswerBtn = document.getElementById('close-answer');
  if (closeAnswerBtn) {
    closeAnswerBtn.addEventListener('click', () => {
      UI.hideAnswer();
    });
  }

  // Copy answer button
  const copyBtn = document.getElementById('copy-answer-button');
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const answerText = document.getElementById('answer-text');
      UI.copyToClipboard(answerText.textContent);
    });
  }
});
