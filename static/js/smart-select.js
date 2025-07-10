/**
 * SmartSelect Widget JavaScript
 * Provides searchable select functionality with pills for selected values
 */

class SmartSelect {
    constructor(container) {
        this.container = container;
        this.name = container.dataset.name;
        this.widgetId = container.dataset.widgetId;
        
        // Get elements
        this.hiddenInput = container.querySelector(`#${this.widgetId}`);
        this.pillsContainer = container.querySelector(`#${this.widgetId}_pills`);
        this.searchInput = container.querySelector(`#${this.widgetId}_search`);
        this.dropdown = container.querySelector(`#${this.widgetId}_dropdown`);
        this.optionsContainer = container.querySelector(`#${this.widgetId}_options`);
        
        # Get data
        const dataScript = container.querySelector('.smart-select-data');
        if (dataScript) {
            try {
                console.log('Raw JSON data:', dataScript.textContent);
                const data = JSON.parse(dataScript.textContent);
                console.log('Parsed data:', data);
                this.choices = data.choices || [];
                this.selectedChoices = data.selected || [];
            } catch (e) {
                console.error('Error parsing SmartSelect data:', e);
                console.log('Failed to parse:', dataScript.textContent);
                this.choices = [];
                this.selectedChoices = [];
            }
        } else {
            console.error('No data script found for:', this.widgetId);
            this.choices = [];
            this.selectedChoices = [];
        }
        
        // State
        this.isOpen = false;
        this.highlightedIndex = -1;
        this.filteredChoices = [...this.choices];
        
        this.init();
    }
    
    init() {
        console.log('SmartSelect initializing for:', this.widgetId);
        console.log('Choices:', this.choices);
        console.log('Selected:', this.selectedChoices);
        this.renderPills();
        this.renderOptions();
        this.bindEvents();
        this.updateHiddenInput();
    }
    
    bindEvents() {
        // Search input events
        this.searchInput.addEventListener('input', (e) => this.handleSearch(e));
        this.searchInput.addEventListener('focus', () => this.openDropdown());
        this.searchInput.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // Click outside to close
        document.addEventListener('click', (e) => {
            if (!this.container.contains(e.target)) {
                this.closeDropdown();
            }
        });
        
        // Prevent dropdown close on scroll
        this.dropdown.addEventListener('scroll', (e) => e.stopPropagation());
    }
    
    handleSearch(e) {
        const query = e.target.value.toLowerCase().trim();
        
        if (query === '') {
            this.filteredChoices = [...this.choices];
        } else {
            this.filteredChoices = this.choices.filter(choice => 
                choice.label.toLowerCase().includes(query)
            );
        }
        
        this.highlightedIndex = -1;
        this.renderOptions();
        this.openDropdown();
    }
    
    handleKeydown(e) {
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.highlightedIndex = Math.min(
                    this.highlightedIndex + 1, 
                    this.filteredChoices.length - 1
                );
                this.updateHighlight();
                this.openDropdown();
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                this.highlightedIndex = Math.max(this.highlightedIndex - 1, -1);
                this.updateHighlight();
                break;
                
            case 'Enter':
                e.preventDefault();
                if (this.highlightedIndex >= 0 && this.isOpen) {
                    this.selectChoice(this.filteredChoices[this.highlightedIndex]);
                }
                break;
                
            case 'Escape':
                this.closeDropdown();
                this.searchInput.blur();
                break;
                
            case 'Backspace':
                if (this.searchInput.value === '' && this.selectedChoices.length > 0) {
                    this.removeChoice(this.selectedChoices[this.selectedChoices.length - 1]);
                }
                break;
        }
    }
    
    openDropdown() {
        this.isOpen = true;
        this.dropdown.classList.add('show');
        this.container.classList.add('open');
    }
    
    closeDropdown() {
        this.isOpen = false;
        this.dropdown.classList.remove('show');
        this.container.classList.remove('open');
        this.highlightedIndex = -1;
        this.updateHighlight();
    }
    
    selectChoice(choice) {
        // Check if already selected
        const isSelected = this.selectedChoices.some(selected => selected.value === choice.value);
        
        if (!isSelected) {
            this.selectedChoices.push(choice);
            this.renderPills();
            this.updateHiddenInput();
        }
        
        // Clear search and close dropdown
        this.searchInput.value = '';
        this.filteredChoices = [...this.choices];
        this.renderOptions();
        this.closeDropdown();
        
        // Focus back to search input
        this.searchInput.focus();
    }
    
    removeChoice(choice) {
        this.selectedChoices = this.selectedChoices.filter(selected => 
            selected.value !== choice.value
        );
        this.renderPills();
        this.renderOptions();
        this.updateHiddenInput();
    }
    
    renderPills() {
        this.pillsContainer.innerHTML = '';
        
        this.selectedChoices.forEach(choice => {
            const pill = document.createElement('div');
            pill.className = 'smart-select-pill';
            pill.innerHTML = `
                <span class="pill-text" title="${this.escapeHtml(choice.label)}">${this.escapeHtml(choice.label)}</span>
                <button type="button" class="pill-remove" aria-label="Eliminar ${this.escapeHtml(choice.label)}">
                    <svg width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
                    </svg>
                </button>
            `;
            
            const removeBtn = pill.querySelector('.pill-remove');
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.removeChoice(choice);
            });
            
            this.pillsContainer.appendChild(pill);
        });
    }
    
    renderOptions() {
        this.optionsContainer.innerHTML = '';
        
        if (this.filteredChoices.length === 0) {
            const noResults = document.createElement('div');
            noResults.className = 'smart-select-no-results';
            noResults.textContent = 'No se encontraron resultados';
            this.optionsContainer.appendChild(noResults);
            return;
        }
        
        this.filteredChoices.forEach((choice, index) => {
            const option = document.createElement('div');
            option.className = 'smart-select-option';
            option.textContent = choice.label;
            option.dataset.value = choice.value;
            
            // Mark as selected if already chosen
            if (this.selectedChoices.some(selected => selected.value === choice.value)) {
                option.classList.add('selected');
            }
            
            option.addEventListener('click', () => {
                this.selectChoice(choice);
            });
            
            this.optionsContainer.appendChild(option);
        });
    }
    
    updateHighlight() {
        const options = this.optionsContainer.querySelectorAll('.smart-select-option');
        options.forEach((option, index) => {
            option.classList.toggle('highlighted', index === this.highlightedIndex);
        });
        
        // Scroll highlighted option into view
        if (this.highlightedIndex >= 0 && options[this.highlightedIndex]) {
            options[this.highlightedIndex].scrollIntoView({
                block: 'nearest'
            });
        }
    }
    
    updateHiddenInput() {
        const values = this.selectedChoices.map(choice => choice.value);
        this.hiddenInput.value = values.length > 0 ? values[0] : ''; // Single select for now
        
        // Trigger change event for form validation
        this.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Auto-initialize SmartSelect widgets when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const containers = document.querySelectorAll('.smart-select-container');
    containers.forEach(container => {
        new SmartSelect(container);
    });
});

// Also initialize when new elements are added dynamically (for formsets)
const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
        mutation.addedNodes.forEach(function(node) {
            if (node.nodeType === 1) { // Element node
                // Check if the added node is a smart-select container
                if (node.classList && node.classList.contains('smart-select-container')) {
                    new SmartSelect(node);
                }
                // Or check if it contains smart-select containers
                const containers = node.querySelectorAll && node.querySelectorAll('.smart-select-container');
                if (containers) {
                    containers.forEach(container => {
                        new SmartSelect(container);
                    });
                }
            }
        });
    });
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SmartSelect;
}