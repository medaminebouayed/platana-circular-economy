import { Component, OnInit } from '@angular/core';
import { ApiService, CatalogModel } from '../services/api.service';
import { AuthService } from '../services/auth.service';
import { TranslationService } from '../services/translation.service';
import { SelectOption } from '../searchable-select/searchable-select.component';

type SubmitStep = 'form' | 'processing' | 'done' | 'error';

@Component({
  selector: 'app-user-portal',
  templateUrl: './user-portal.component.html',
  styleUrls: ['./user-portal.component.css']
})
export class UserPortalComponent implements OnInit {
  currentStep: SubmitStep = 'form';
  errorMessage = '';

  form = {
    brand: '',
    model: '',
    year: new Date().getFullYear() - 2,
    originalPrice: 0,
  };

  // Image handling
  uploadedFiles: File[] = [];
  previewUrls: string[] = [];
  dragOver = false;

  // Result
  submittedProductId: string | null = null;
  evaluationResult: any = null;
  processingSteps: { label: string; status: 'pending' | 'running' | 'done' }[] = [];

  categories = ['Smartphone', 'Ordinateur portable', 'Tablette', 'TV', 'Casque Audio', 'Console de jeux', 'Aspirateur', 'Autre'];
  brandOptions: SelectOption[] = [];
  modelOptions: SelectOption[] = [];
  brandLoading = false;
  modelLoading = false;
  catalogError = '';

  activeTab: 'submit' | 'history' = 'submit';
  userProducts: any[] = [];
  isLoadingHistory = false;
  reportLoadingId: string | null = null;

  constructor(private api: ApiService, public authService: AuthService, private translation: TranslationService) {}

  ngOnInit() {
    this.loadUserProducts();
  }

  loadUserProducts() {
    const email = this.authService.currentUserValue?.email;
    if (!email) return;
    this.isLoadingHistory = true;
    this.api.getUserProducts(email).subscribe({
      next: (products) => {
        this.userProducts = products;
        this.isLoadingHistory = false;
      },
      error: () => this.isLoadingHistory = false
    });
  }

  onBrandOpen() {
    this.loadBrands(this.form.brand || '');
  }

  onBrandInput(query: string) {
    this.catalogError = '';
    this.form.brand = query;
    this.modelOptions = [];
    this.form.model = '';
    this.loadBrands(query);
  }

  onBrandSelected(option: SelectOption) {
    this.form.brand = option.value || option.label;
    this.catalogError = '';
    this.form.model = '';
    this.modelOptions = [];
    this.loadModels('');
  }

  loadBrands(query: string) {
    this.brandLoading = true;
    this.api.searchCatalogBrands((query || '').trim()).subscribe({
      next: response => {
        this.brandOptions = response.items.map(b => ({ label: b, value: b }));
        this.brandLoading = false;
      },
      error: () => {
        this.brandLoading = false;
        this.catalogError = this.translation.t('portal.catalogUnavailable');
      }
    });
  }

  onModelOpen() {
    if (!this.form.brand.trim()) return;
    this.loadModels(this.form.model || '');
  }

  onModelInput(query: string) {
    if (!this.form.brand.trim()) return;
    this.form.model = query;
    this.loadModels(query);
  }

  onModelSelected(option: SelectOption) {
    this.selectModelOption(option);
  }

  loadModels(query: string) {
    this.modelLoading = true;
    this.api.searchCatalogModels(this.form.brand, (query || '').trim()).subscribe({
      next: response => {
        this.modelOptions = response.items.map(item => ({
          label: item.model,
          subLabel: `${item.category} · ${item.original_price} €`,
          value: item.model,
          data: item as unknown as Record<string, unknown>,
        }));
        this.modelLoading = false;
        if (this.modelOptions.length === 1 && !query.trim()) {
          this.selectModelOption(this.modelOptions[0]);
        }
      },
      error: () => {
        this.modelLoading = false;
        this.catalogError = this.translation.t('portal.catalogModelsError');
      }
    });
  }

  selectModelOption(option: SelectOption) {
    this.form.model = option.value || option.label;
    const catalog = option.data as CatalogModel | undefined;
    if (catalog?.original_price) {
      this.form.originalPrice = catalog.original_price;
    }
  }

  onDragOver(event: DragEvent) { event.preventDefault(); this.dragOver = true; }
  onDragLeave() { this.dragOver = false; }
  onDrop(event: DragEvent) {
    event.preventDefault(); this.dragOver = false;
    this.addFiles(Array.from(event.dataTransfer?.files || []));
  }
  onFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    this.addFiles(Array.from(input?.files || []));
  }
  private addFiles(files: File[]) {
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    const toAdd = imageFiles.slice(0, 5 - this.uploadedFiles.length);
    toAdd.forEach(file => {
      this.uploadedFiles.push(file);
      const reader = new FileReader();
      reader.onload = (e: any) => this.previewUrls.push(e.target.result);
      reader.readAsDataURL(file);
    });
  }
  removeFile(i: number) {
    this.uploadedFiles.splice(i, 1);
    this.previewUrls.splice(i, 1);
  }

  isFormValid(): boolean {
    return !!(this.form.brand && this.form.model && this.form.originalPrice > 0);
  }

  submitProduct() {
    if (!this.isFormValid()) return;

    this.currentStep = 'processing';
    this.processingSteps = [
      { label: this.translation.t('portal.stepUpload'), status: 'running' },
      { label: this.translation.t('portal.stepVision'), status: 'pending' },
      { label: this.translation.t('portal.stepPricing'), status: 'pending' },
      { label: this.translation.t('portal.stepGenAI'), status: 'pending' },
      { label: this.translation.t('portal.stepValidation'), status: 'pending' },
    ];

    this.api.uploadAndEvaluate({
      brand: this.form.brand,
      model: this.form.model,
      year: this.form.year,
      original_price: this.form.originalPrice,
      user_email: this.authService.currentUserValue?.email || 'anonymous@platana.fr',
      files: this.uploadedFiles,
    }).subscribe({
      next: (response) => {
        this.submittedProductId = response.product_id;
        this.processingSteps.forEach(s => s.status = 'done');
        this.evaluationResult = response.ai_predictions;
        this.currentStep = 'done';
        this.loadUserProducts(); // Refresh history
      },
      error: (err) => {
        this.processingSteps.forEach(s => s.status = 'done');
        this.errorMessage = err?.error?.detail || this.translation.t('portal.serverError');
        this.currentStep = 'error';
        console.error('Erreur API:', err);
      }
    });
  }

  reset() {
    this.currentStep = 'form';
    this.form = { brand: '', model: '', year: new Date().getFullYear() - 2, originalPrice: 0 };
    this.uploadedFiles = [];
    this.previewUrls = [];
    this.submittedProductId = null;
    this.evaluationResult = null;
    this.errorMessage = '';
  }

  getGradeColor(grade: string): string {
    const map: Record<string, string> = { A: '#10b981', B: '#0ea5e9', C: '#f59e0b', D: '#ef4444' };
    return map[grade] || '#94a3b8';
  }

  getDecisionLabel(decision: string): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: this.translation.t('portal.dec.RESALE_DIRECT'),
      RECONDITION: this.translation.t('portal.dec.RECONDITION'),
      RECYCLE: this.translation.t('portal.dec.RECYCLE'),
    };
    return map[decision] || decision;
  }

  getStatusLabel(status: string): string {
    const map: Record<string, string> = {
      PENDING_EVALUATION: this.translation.t('dashboard.status.PENDING_EVALUATION'),
      PENDING_ADMIN_REVIEW: this.translation.t('dashboard.status.PENDING_ADMIN_REVIEW'),
      REVIEW_READY: this.translation.t('dashboard.status.REVIEW_READY'),
      REVIEWED: this.translation.t('dashboard.status.REVIEWED'),
      PUBLISHED: this.translation.t('dashboard.status.PUBLISHED'),
      REJECTED: this.translation.t('dashboard.status.REJECTED'),
      AI_ERROR: this.translation.t('dashboard.status.AI_ERROR'),
      PUBLISH_ERROR: this.translation.t('dashboard.status.PUBLISH_ERROR'),
    };
    return map[status] || status;
  }

  getEffectiveTitle(product: any): string {
    return product.admin_review?.title || product.ai_predictions?.title || '';
  }

  getEffectiveDescription(product: any): string {
    return product.admin_review?.description || product.ai_predictions?.description || '';
  }

  canDownloadReport(product: any): boolean {
    if (product.status === 'AI_ERROR') return false;
    return !!(product.report_path || product.ai_predictions || product.admin_review);
  }

  downloadReport(product: any): void {
    if (this.reportLoadingId) return;
    this.reportLoadingId = product.id;
    this.api.getProductReport(product.id).subscribe({
      next: (blob) => {
        this.reportLoadingId = null;
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `platana_report_${product.id}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      },
      error: () => {
        this.reportLoadingId = null;
        alert(this.translation.t('portal.reportError'));
      }
    });
  }
}
