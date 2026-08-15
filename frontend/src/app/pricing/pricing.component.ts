import { Component } from '@angular/core';

import { AuthService } from '../services/auth.service';
import { ApiService } from '../services/api.service';
import { TranslationService } from '../services/translation.service';

@Component({
  selector: 'app-pricing',
  templateUrl: './pricing.component.html',
  styleUrls: ['./pricing.component.css']
})
export class PricingComponent {
  form: any = {
    grade: 'B',
    category: 'Smartphone',
    brand: 'Samsung',
    model: 'Galaxy S22',
    original_price: 849,
    age_days: 365,
    repair_cost: 30,
    season: 'autumn'
  };

  result: any | null = null;
  isLoading = false;
  history: Array<{ request: any; result: any }> = [];

  // Admin Override
  isValidationMode = false;
  adminOverriddenPrice: number | null = null;
  isApprovedForMarketplace = false;

  categories = ['Smartphone', 'Ordinateur', 'Tablette', 'TV', 'Aspirateur', 'Audio', 'Outillage', 'Electroménager', 'Console de jeux', 'Appareil photo'];
  grades = ['A', 'B', 'C', 'D'];
  seasons = [
    { value: 'spring', label: 'Printemps' },
    { value: 'summer', label: 'Été' },
    { value: 'autumn', label: 'Automne' },
    { value: 'winter', label: 'Hiver' },
  ];

  // Preset products for quick demo
  presets = [
    { label: 'iPhone 13 Pro', grade: 'A', category: 'Smartphone', brand: 'Apple', model: 'iPhone 13 Pro', original_price: 1159, age_days: 500, repair_cost: 0 },
    { label: 'Galaxy S22', grade: 'B', category: 'Smartphone', brand: 'Samsung', model: 'Galaxy S22', original_price: 849, age_days: 365, repair_cost: 30 },
    { label: 'MacBook Air M1', grade: 'A', category: 'Ordinateur', brand: 'Apple', model: 'MacBook Air M1', original_price: 1299, age_days: 600, repair_cost: 0 },
    { label: 'Dyson V11', grade: 'C', category: 'Aspirateur', brand: 'Dyson', model: 'V11 Absolute', original_price: 549, age_days: 720, repair_cost: 75 },
  ];

  constructor(
    public authService: AuthService,
    private api: ApiService,
    public translation: TranslationService
  ) {}

  applyPreset(preset: any) {
    this.form = { ...preset, season: 'autumn' };
    this.result = null;
  }

  estimate() {
    this.isLoading = true;
    this.result = null;
    this.api.predictPrice(this.form).subscribe({
      next: (res) => {
        this.isLoading = false;
        this.result = res;
        if (this.result) {
          this.history.unshift({ request: { ...this.form }, result: this.result });
          if (this.history.length > 5) this.history.pop();
        }
      },
      error: () => {
        this.isLoading = false;
        this.result = null;
      }
    });
  }

  getPriceRatioPct(): number {
    return Math.round((this.result?.price_ratio || 0) * 100);
  }

  getPriceRatioColor(): string {
    const pct = this.getPriceRatioPct();
    if (pct >= 65) return '#10b981';
    if (pct >= 45) return '#f59e0b';
    return '#ef4444';
  }

  getMargin(): number {
    if (!this.result) return 0;
    const repairCost = this.form.repair_cost || 0;
    return Math.round(this.result.predicted_price - repairCost);
  }

  getGradeLabel(g: string) {
    const map: Record<string, string> = {
      A: this.translation.t('pricing.gradeDesc.A'),
      B: this.translation.t('pricing.gradeDesc.B'),
      C: this.translation.t('pricing.gradeDesc.C'),
      D: this.translation.t('pricing.gradeDesc.D'),
    };
    return map[g] || g;
  }
}
