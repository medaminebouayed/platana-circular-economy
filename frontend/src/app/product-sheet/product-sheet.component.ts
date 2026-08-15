import { Component } from '@angular/core';

import { ApiService } from '../services/api.service';
import { TranslationService } from '../services/translation.service';

@Component({
  selector: 'app-product-sheet',
  templateUrl: './product-sheet.component.html',
  styleUrls: ['./product-sheet.component.css']
})
export class ProductSheetComponent {
  form = {
    productId: '',
    brand: 'Samsung',
    model: 'Galaxy S22',
    category: 'Smartphone',
    grade: 'B',
    originalPrice: 849,
    predictedPrice: 349,
    repairCost: 30,
    defects: [] as string[],
  };

  defectOptions = [
    { value: 'scratch', label: this.translation.t('sheet.defect.scratch') },
    { value: 'dent', label: this.translation.t('sheet.defect.dent') },
    { value: 'crack', label: this.translation.t('sheet.defect.crack') },
    { value: 'discoloration', label: this.translation.t('sheet.defect.discoloration') },
    { value: 'missing_part', label: this.translation.t('sheet.defect.missing_part') },
    { value: 'water_damage', label: this.translation.t('sheet.defect.water_damage') },
  ];

  categories = ['Smartphone', 'Ordinateur', 'Tablette', 'TV', 'Aspirateur', 'Audio', 'Outillage', 'Console de jeux'];
  grades = ['A', 'B', 'C', 'D'];

  result: any | null = null;
  isLoading = false;
  isPublishing = false;
  publishedChannels: string[] = [];
  displayedText = '';
  private typewriterInterval: any;

  publishSteps: Array<{ label: string; status: 'pending' | 'running' | 'done' | 'error' }> = [];

  constructor(private translation: TranslationService, private api: ApiService) {}

  toggleDefect(value: string) {
    const idx = this.form.defects.indexOf(value);
    if (idx > -1) {
      this.form.defects.splice(idx, 1);
    } else {
      this.form.defects.push(value);
    }
  }

  generate() {
    this.isLoading = true;
    this.result = null;
    this.publishedChannels = [];
    this.publishSteps = [];
    clearInterval(this.typewriterInterval);
    this.displayedText = '';

    this.api.generateSheet(this.form).subscribe({
      next: (res) => {
        this.isLoading = false;
        this.result = res;
        this.startTypewriter(res.description);
      },
      error: () => {
        this.isLoading = false;
        this.result = null;
      }
    });
  }

  private startTypewriter(fullText: string) {
    this.displayedText = '';
    let i = 0;
    const speed = 18;
    clearInterval(this.typewriterInterval);
    this.typewriterInterval = setInterval(() => {
      if (i < fullText.length) {
        this.displayedText += fullText.charAt(i);
        i++;
      } else {
        clearInterval(this.typewriterInterval);
      }
    }, speed);
  }

  simulatePublish() {
    if (!this.result) return;
    this.isPublishing = true;
    this.publishSteps = (this.result.recommended_channels || []).map((ch: string) => ({
      label: ch, status: 'pending'
    }));

    this.publishSteps.forEach((step, i) => {
      setTimeout(() => {
        step.status = 'running';
        setTimeout(() => {
          step.status = 'done';
          this.publishedChannels.push(step.label);
          if (i === this.publishSteps.length - 1) {
            this.isPublishing = false;
          }
        }, 1200);
      }, i * 1500);
    });
  }

  getDecisionColor(): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: '#10b981',
      RECONDITION: '#f59e0b',
      RECYCLE: '#ef4444',
      HOLD: '#0ea5e9',
    };
    return map[this.result?.decision || ''] || '#94a3b8';
  }

  getDecisionIcon(): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: '✅',
      RECONDITION: '🔧',
      RECYCLE: '♻️',
      HOLD: '⏸️',
    };
    return map[this.result?.decision || ''] || '❓';
  }

  getDecisionLabel(): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: this.translation.t('sheet.decision.RESALE_DIRECT'),
      RECONDITION: this.translation.t('sheet.decision.RECONDITION'),
      RECYCLE: this.translation.t('sheet.decision.RECYCLE'),
      HOLD: this.translation.t('sheet.decision.HOLD'),
    };
    return map[this.result?.decision || ''] || '';
  }

  isDefectSelected(value: string): boolean {
    return this.form.defects.includes(value);
  }
}
