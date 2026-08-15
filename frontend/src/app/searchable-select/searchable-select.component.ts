import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnDestroy,
  ElementRef,
  ViewChild,
} from '@angular/core';

export interface SelectOption {
  label: string;
  subLabel?: string;
  value?: string;
  data?: Record<string, unknown>;
}

@Component({
  selector: 'app-searchable-select',
  templateUrl: './searchable-select.component.html',
  styleUrls: ['./searchable-select.component.css']
})
export class SearchableSelectComponent implements OnDestroy {
  @Input() placeholder = '';
  @Input() disabled = false;
  @Input() loading = false;
  @Input() emptyMessage = '—';
  @Input() loadingMessage = '…';
  @Input() options: SelectOption[] = [];
  @Input() value = '';
  @Output() valueChange = new EventEmitter<string>();
  @Output() selected = new EventEmitter<SelectOption>();
  @Output() opened = new EventEmitter<void>();

  @ViewChild('filterInput') filterInput?: ElementRef<HTMLInputElement>;

  open = false;
  filter = '';
  private outsideClickListener: ((event: Event) => void) | null = null;

  constructor(private host: ElementRef<HTMLElement>) {}

  get filteredOptions(): SelectOption[] {
    if (!this.filter.trim()) return this.options;
    const q = this.filter.toLowerCase();
    return this.options.filter(o =>
      o.label.toLowerCase().includes(q) ||
      (o.subLabel && o.subLabel.toLowerCase().includes(q))
    );
  }

  toggleOpen(event: Event) {
    event.stopPropagation();
    if (this.disabled) return;
    this.open = !this.open;
    if (this.open) {
      this.filter = this.value || '';
      this.opened.emit();
      this.addOutsideClickListener();
      setTimeout(() => this.filterInput?.nativeElement.focus(), 0);
    } else {
      this.removeOutsideClickListener();
    }
  }

  onFilterInput(event: Event) {
    this.filter = (event.target as HTMLInputElement).value;
    this.valueChange.emit(this.filter);
  }

  selectOption(option: SelectOption, event: Event) {
    event.preventDefault();
    event.stopPropagation();
    this.value = option.label;
    this.filter = option.label;
    this.selected.emit(option);
    this.close();
  }

  close() {
    this.open = false;
    this.removeOutsideClickListener();
  }

  isSelected(option: SelectOption): boolean {
    const current = (this.value || '').trim().toLowerCase();
    return current === option.label.trim().toLowerCase();
  }

  private addOutsideClickListener() {
    setTimeout(() => {
      this.outsideClickListener = (event: Event) => {
        if (!this.host.nativeElement.contains(event.target as Node)) {
          this.close();
        }
      };
      document.addEventListener('click', this.outsideClickListener, true);
    }, 0);
  }

  private removeOutsideClickListener() {
    if (this.outsideClickListener) {
      document.removeEventListener('click', this.outsideClickListener, true);
      this.outsideClickListener = null;
    }
  }

  ngOnDestroy() {
    this.removeOutsideClickListener();
  }
}
