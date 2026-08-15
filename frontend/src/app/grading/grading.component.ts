import { Component } from '@angular/core';

import { AuthService } from '../services/auth.service';
import { ApiService } from '../services/api.service';
import { TranslationService } from '../services/translation.service';

@Component({
  selector: 'app-grading',
  templateUrl: './grading.component.html',
  styleUrls: ['./grading.component.css']
})
export class GradingComponent {
  uploadedFiles: File[] = [];
  previewUrls: string[] = [];
  productId = '';
  isLoading = false;
  result: any | null = null;
  error = '';
  dragOver = false;

  // Fields for immediate pricing estimation
  category = 'smartphone';
  brand = 'Apple';
  model = 'iPhone 13 Pro';
  originalPrice = 999.0;
  pricingResult: any = null;
  isPricingLoading = false;

  defectLabels: { [key: string]: string } = {
    scratch: this.translation.t('grading.defect.scratch'),
    dent: this.translation.t('grading.defect.dent'),
    crack: this.translation.t('grading.defect.crack'),
    discoloration: this.translation.t('grading.defect.discoloration'),
    missing_part: this.translation.t('grading.defect.missing_part'),
    water_damage: this.translation.t('grading.defect.water_damage')
  };

  // Admin Override
  isValidationMode = false;
  adminOverriddenGrade: string | null = null;
  adminApproved = false;

  constructor(
    public authService: AuthService,
    private api: ApiService,
    public translation: TranslationService
  ) {}

  tWith(key: string, params?: Record<string, string | number>): string {
    return this.translation.tWith(key, params || {});
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.dragOver = true;
  }

  onDragLeave() {
    this.dragOver = false;
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragOver = false;
    const files = Array.from(event.dataTransfer?.files || []);
    this.addFiles(files);
  }

  onFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input?.files || []);
    this.addFiles(files);
  }

  private addFiles(files: File[]) {
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    const remaining = 5 - this.uploadedFiles.length;
    const toAdd = imageFiles.slice(0, remaining);

    toAdd.forEach(file => {
      this.uploadedFiles.push(file);
      const reader = new FileReader();
      reader.onload = (e: any) => {
        this.previewUrls.push(e.target.result);
      };
      reader.readAsDataURL(file);
    });
  }

  removeFile(index: number) {
    this.uploadedFiles.splice(index, 1);
    this.previewUrls.splice(index, 1);
  }

  analyze() {
    if (this.uploadedFiles.length === 0) return;
    this.isLoading = true;
    this.result = null;
    this.pricingResult = null;
    this.error = '';

    this.api.gradeImages(this.uploadedFiles).subscribe({
      next: (res) => {
        this.isLoading = false;
        const grade = res.grade || 'C';
        const conf = Math.min(0.98, Math.max(0.5, Number(res.grade_confidence ?? 1)));
        const rest = Math.round((1 - conf) * 1000) / 1000 / 3;
        this.result = {
          grade,
          grade_confidence: conf,
          num_views_used: this.uploadedFiles.length,
          processing_time_ms: 0,
          grade_probabilities: { A: rest, B: rest, C: rest, D: rest, [grade]: conf },
          detected_defects: (res.detected_defects || [])
            .filter((d: string) => d && d !== 'no_defect')
            .map((d: string) => ({
            type: d,
            probability: 1,
            label: this.defectLabel(d),
          })),
          product_id: this.productId || undefined,
        };
        this.isValidationMode = true;
        this.adminOverriddenGrade = grade;
        this.fetchPricing(grade);
      },
      error: (err) => {
        this.isLoading = false;
        this.error = err?.error?.detail || this.translation.t('grading.analysisError');
      }
    });
  }

  fetchPricing(grade: string) {
    if (!this.brand || !this.model) return;
    this.isPricingLoading = true;
    this.pricingResult = null;
    const defects = this.result?.detected_defects?.map((d: any) => d.type) || [];
    this.api.predictPrice({
      grade,
      category: this.category,
      brand: this.brand,
      model: this.model,
      original_price: this.originalPrice || 999,
      age_days: 365,
      repair_cost: 0,
      defects
    }).subscribe({
      next: (res) => {
        this.isPricingLoading = false;
        this.pricingResult = {
          predicted_price: res.predicted_price,
          price_ratio: res.price_ratio || 0,
          confidence_interval: res.confidence_interval || [0, 0],
          explanation: this.translation.t('grading.pricingExplanation'),
        };
      },
      error: () => {
        this.isPricingLoading = false;
        this.pricingResult = null;
      }
    });
  }

  defectLabel(defectId: string): string {
    const key = `grading.defect.${defectId}`;
    const translated = this.translation.t(key);
    return translated !== key ? translated : this.translation.t(`grading.defect.${defectId.split('_')[0]}`) || defectId;
  }

  onAdminGradeChange() {
    if (this.adminOverriddenGrade) {
      this.fetchPricing(this.adminOverriddenGrade);
    }
  }

  confirmValidation() {
    this.adminApproved = true;
    // In a real app, we would save this to the database
    // For now, it updates the local state so the admin knows it's validated
    console.log("Admin validated grade: ", this.adminOverriddenGrade);
  }

  reset() {
    this.uploadedFiles = [];
    this.previewUrls = [];
    this.result = null;
    this.pricingResult = null;
    this.productId = '';
    this.category = 'smartphone';
    this.brand = 'Apple';
    this.model = 'iPhone 13 Pro';
    this.originalPrice = 999.0;
    this.isValidationMode = false;
    this.adminOverriddenGrade = null;
    this.adminApproved = false;
  }

  getGradeColor(grade: string): string {
    const map: { [key: string]: string } = {
      'A': '#10b981',
      'B': '#0ea5e9',
      'C': '#f59e0b',
      'D': '#ef4444'
    };
    return map[grade] || '#94a3b8';
  }

  getGradeLabel(grade: string): string {
    const map: { [key: string]: string } = {
      'A': this.translation.t('grading.gradeDesc.A'),
      'B': this.translation.t('grading.gradeDesc.B'),
      'C': this.translation.t('grading.gradeDesc.C'),
      'D': this.translation.t('grading.gradeDesc.D')
    };
    return map[grade] || '';
  }

  getAttentionWeight(index: number): number {
    if (!this.result?.attention_weights) return 0;
    const weights = this.result.attention_weights;
    const max = Math.max(...weights);
    return max > 0 ? (weights[index] / max) * 100 : 0;
  }

  getConfidencePct(): number {
    return Math.round((this.result?.grade_confidence || 0) * 100);
  }

  getProbPct(grade: string): number {
    return Math.round((this.result?.grade_probabilities[grade] || 0) * 100);
  }
}
