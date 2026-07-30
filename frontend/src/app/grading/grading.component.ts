import { Component } from '@angular/core';
import { ApiService, GradingResponse } from '../services/api.service';

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
  result: GradingResponse | null = null;
  dragOver = false;

  // Fields for immediate pricing estimation
  category = 'smartphone';
  brand = 'Apple';
  model = 'iPhone 13 Pro';
  originalPrice = 999.0;
  pricingResult: any = null;
  isPricingLoading = false;

  defectLabels: { [key: string]: string } = {
    scratch: 'Rayure',
    dent: 'Enfoncement / Choc',
    crack: 'Fissure',
    discoloration: 'Décoloration',
    missing_part: 'Pièce manquante',
    water_damage: 'Dégât des eaux'
  };

  constructor(public apiService: ApiService) {}

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

    this.apiService.gradeProduct(this.uploadedFiles, this.productId || undefined).subscribe({
      next: (res) => {
        this.result = res;
        this.isLoading = false;
        
        // Immediately fetch predicted price based on detected grade
        this.isPricingLoading = true;
        this.apiService.predictPrice({
          grade: res.grade,
          category: this.category,
          brand: this.brand,
          model: this.model,
          original_price: this.originalPrice,
          age_days: 180, // Default simulated age (6 months)
          repair_cost: res.grade === 'C' ? 50.0 : (res.grade === 'D' ? 120.0 : 0.0)
        }).subscribe({
          next: (priceRes) => {
            this.pricingResult = priceRes;
            this.isPricingLoading = false;
          },
          error: () => {
            this.isPricingLoading = false;
          }
        });
      },
      error: () => {
        this.isLoading = false;
      }
    });
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
      'A': 'Excellent État — Revente directe',
      'B': 'Très Bon État — Revente possible',
      'C': 'État Correct — Reconditionnement conseillé',
      'D': 'Mauvais État — Recyclage recommandé'
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
