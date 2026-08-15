import { Component, OnInit } from '@angular/core';
import { AuthService } from '../services/auth.service';
import { ApiService, ProductSummary, DefectCatalogItem } from '../services/api.service';
import { TranslationService } from '../services/translation.service';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit {

  allProducts: ProductSummary[] = [];
  selectedProduct: ProductSummary | null = null;
  isLoading = true;

  // Admin override state
  adminGrade = '';
  adminPrice = 0;
  adminTitle = '';
  adminDescription = '';
  adminRefurbCost = 0;
  adminDefects: string[] = [];
  defectCatalog: DefectCatalogItem[] = [];
  selectedImageIndex = 0;
  isSaving = false;
  isPublishing = false;
  saveResult: { success: boolean; message: string } | null = null;
  publishResult: { success: boolean; message: string; url?: string } | null = null;

  stats: any = null;
  driftStats: any = null;

  kpis = [
    { key: 'pending', label: this.translation.t('dashboard.kpi.pending'), value: '0', color: 'blue' },
    { key: 'published', label: this.translation.t('dashboard.kpi.published'), value: '0', color: 'green' },
    { key: 'rejected', label: this.translation.t('dashboard.kpi.rejected'), value: '0', color: 'red' },
    { key: 'total', label: this.translation.t('dashboard.kpi.total'), value: '0', color: 'purple' },
  ];

  detailKpis: { label: string; value: string; color: string }[] = [];

  constructor(public authService: AuthService, private api: ApiService, private translation: TranslationService) {}

  ngOnInit() {
    this.loadProducts();
    this.api.getDefectCatalog().subscribe({
      next: res => this.defectCatalog = res.items,
      error: () => this.defectCatalog = []
    });
  }

  loadProducts() {
    this.isLoading = true;
    this.api.getAllProducts().subscribe({
      next: (products) => {
        this.allProducts = products;
        this.loadStats();
      },
      error: () => { this.isLoading = false; }
    });
  }

  loadStats() {
    this.api.getDashboardStats().subscribe(stats => {
      this.stats = stats;
      this.kpis[0].value = stats.totalPending.toString();
      this.kpis[1].value = stats.published.toString();
      this.kpis[2].value = stats.rejected.toString();
      this.kpis[3].value = stats.totalProcessed.toString();
      this.detailKpis = [
        { label: this.translation.t('dashboard.kpi.resale'), value: String(stats.forResale || 0), color: 'green' },
        { label: this.translation.t('dashboard.kpi.recondition'), value: String(stats.forRecondition || 0), color: 'yellow' },
        { label: this.translation.t('dashboard.kpi.recycle'), value: String(stats.forRecycle || 0), color: 'red' },
        { label: this.translation.t('dashboard.kpi.transport'), value: (stats.totalTransportCost || 0) + ' €', color: 'purple' },
      ];
      this.isLoading = false;
    }, () => this.isLoading = false );
    this.api.getDriftStats(30).subscribe({
      next: drift => this.driftStats = drift,
      error: () => this.driftStats = null
    });
  }

  isRejecting = false;
  isReEvaluating = false;

  get pendingProducts(): ProductSummary[] {
    return this.allProducts.filter(p => p.status === 'PENDING_ADMIN_REVIEW');
  }

  get publishedProducts(): ProductSummary[] {
    return this.allProducts.filter(p => p.status === 'PUBLISHED');
  }

  selectProduct(product: ProductSummary) {
    this.selectedProduct = product;
    this.selectedImageIndex = 0;
    const ai = product.ai_predictions;
    const review = product.admin_review;
    this.adminGrade = review?.grade || ai?.grade || 'B';
    this.adminPrice = review?.market_price || ai?.market_price || 0;
    this.adminTitle = review?.title || ai?.title || '';
    this.adminDescription = review?.description || ai?.description || '';
    this.adminRefurbCost = review?.refurb_cost || ai?.refurb_cost || 0;
    this.adminDefects = [...(review?.defects?.length ? review.defects : (ai?.defects || []))];
    this.saveResult = null;
    this.publishResult = null;
  }

  closeDetail() { this.selectedProduct = null; this.saveResult = null; this.publishResult = null; }

  saveReview() {
    if (!this.selectedProduct) return;
    this.isSaving = true;
    const reviewPayload = {
      grade: this.adminGrade,
      defects: this.adminDefects,
      market_price: this.adminPrice,
      refurb_cost: this.adminRefurbCost,
      title: this.adminTitle,
      description: this.adminDescription,
      reviewed_by: this.authService.currentUserValue?.email || 'admin'
    };
    this.api.reviewProduct(this.selectedProduct.id, reviewPayload).subscribe({
      next: () => {
        this.isSaving = false;
        this.saveResult = { success: true, message: this.translation.t('dashboard.saveSuccess') };
        this.loadProducts();
      },
      error: () => {
        this.isSaving = false;
        this.saveResult = { success: false, message: this.translation.t('dashboard.saveError') };
      }
    });
  }

  get gradeDistributionEntries(): { grade: string; shares: number[] }[] {
    const gk: Record<string, number[]> = { A: [0, 100], B: [0, 100], C: [0, 100], D: [0, 100] };
    const dist = this.stats?.gradeDistribution || {};
    const total = Math.max(1, Object.values(dist).reduce((a: number, b: any) => a + Number(b || 0), 0));
    (Object.keys(gk) as string[]).forEach(g => {
      if (dist[g] !== undefined) {
        const pct = Math.round((Number(dist[g]) / total) * 100);
        gk[g] = [Number(dist[g]), pct];
      }
    });
    return [{ grade: 'A', shares: gk['A'] }, { grade: 'B', shares: gk['B'] }, { grade: 'C', shares: gk['C'] }, { grade: 'D', shares: gk['D'] }];
  }

  rejectProduct() {
    if (!this.selectedProduct) return;
    if (!confirm(this.translation.tWith('dashboard.rejectConfirm', { name: `${this.selectedProduct.brand} ${this.selectedProduct.model}` }))) return;
    this.isRejecting = true;
    this.api.rejectProduct(this.selectedProduct.id).subscribe({
      next: () => {
        this.isRejecting = false;
        this.saveResult = { success: true, message: this.translation.t('dashboard.rejectSuccess') };
        if (this.selectedProduct) this.selectedProduct.status = 'REJECTED';
        this.loadProducts();
      },
      error: (err) => {
        this.isRejecting = false;
        this.saveResult = { success: false, message: err?.error?.detail || this.translation.t('dashboard.rejectError') };
      }
    });
  }

  reEvaluateProduct() {
    if (!this.selectedProduct) return;
    this.isReEvaluating = true;
    this.saveResult = null;
    this.api.reEvaluateProduct(this.selectedProduct.id).subscribe({
      next: (res) => {
        this.isReEvaluating = false;
        this.saveResult = { success: true, message: this.translation.t('dashboard.reevalSuccess') };
        if (this.selectedProduct) {
          this.selectedProduct.status = 'PENDING_ADMIN_REVIEW';
          this.selectedProduct.ai_predictions = res.ai_predictions;
          this.selectProduct(this.selectedProduct);
        }
        this.loadProducts();
      },
      error: (err) => {
        this.isReEvaluating = false;
        this.saveResult = { success: false, message: err?.error?.detail || this.translation.t('dashboard.reevalError') };
      }
    });
  }

  publishProduct() {
    if (!this.selectedProduct) return;
    this.isPublishing = true;
    this.publishResult = null;
    this.api.publishProduct(this.selectedProduct.id).subscribe({
      next: (res) => {
        this.isPublishing = false;
        this.publishResult = { success: true, message: this.translation.t('dashboard.publishSuccess'), url: res.shopify_url };
        this.loadProducts();
      },
      error: (err) => {
        this.isPublishing = false;
        const detail = err?.error?.detail || this.translation.t('dashboard.publishError');
        this.publishResult = { success: false, message: detail };
      }
    });
  }

  getGradeColor(grade: string): string {
    const map: Record<string, string> = { A: '#10b981', B: '#0ea5e9', C: '#f59e0b', D: '#ef4444' };
    return map[grade] || '#94a3b8';
  }

  getStatusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      PENDING_EVALUATION: 'badge badge-info',
      PENDING_ADMIN_REVIEW: 'badge badge-warning',
      REVIEWED: 'badge badge-info',
      PUBLISHED: 'badge badge-success',
      REJECTED: 'badge badge-danger',
      AI_ERROR: 'badge badge-danger',
    };
    return map[status] || 'badge';
  }

  getStatusLabel(status: string): string {
    const map: Record<string, string> = {
      PENDING_EVALUATION: this.translation.t('dashboard.status.PENDING_EVALUATION'),
      PENDING_ADMIN_REVIEW: this.translation.t('dashboard.status.PENDING_ADMIN_REVIEW'),
      REVIEW_READY: this.translation.t('dashboard.status.REVIEW_READY'),
      AI_EVALUATED: this.translation.t('dashboard.status.AI_EVALUATED'),
      REVIEWED: this.translation.t('dashboard.status.REVIEWED'),
      PUBLISHED: this.translation.t('dashboard.status.PUBLISHED'),
      REJECTED: this.translation.t('dashboard.status.REJECTED'),
      AI_ERROR: this.translation.t('dashboard.status.AI_ERROR'),
      PUBLISH_ERROR: this.translation.t('dashboard.status.PUBLISH_ERROR'),
    };
    return map[status] || status;
  }

  getDecisionLabel(decision?: string): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: this.translation.t('dashboard.dec.RESALE_DIRECT'),
      RECONDITION: this.translation.t('dashboard.dec.RECONDITION'),
      RECYCLE: this.translation.t('dashboard.dec.RECYCLE'),
    };
    return decision ? (map[decision] || decision) : '—';
  }

  defectLabel(defectId: string): string {
    const key = `grading.defect.${defectId}`;
    const translated = this.translation.t(key);
    return translated !== key ? translated : defectId;
  }

  isDefectSelected(defectId: string): boolean {
    return this.adminDefects.includes(defectId);
  }

  toggleDefect(defectId: string): void {
    const idx = this.adminDefects.indexOf(defectId);
    if (idx > -1) {
      this.adminDefects.splice(idx, 1);
    } else {
      this.adminDefects.push(defectId);
    }
  }

  get imageCount(): number {
    return this.selectedProduct?.image_paths?.length || 0;
  }

  isReportLoading = false;
  isDeleting = false;

  get hasReport(): boolean {
    if (!this.selectedProduct) return false;
    if (this.selectedProduct.report_path) return true;
    return !!(this.selectedProduct.ai_predictions || this.selectedProduct.admin_review);
  }

  get effectiveTitle(): string {
    const p = this.selectedProduct;
    if (!p) return '';
    return p.admin_review?.title || p.ai_predictions?.title || '';
  }

  get effectiveDescription(): string {
    const p = this.selectedProduct;
    if (!p) return '';
    return p.admin_review?.description || p.ai_predictions?.description || '';
  }

  downloadReport(): void {
    if (!this.selectedProduct || !this.selectedProduct.report_path) return;
    this.isReportLoading = true;
    this.api.getProductReport(this.selectedProduct.id).subscribe({
      next: (blob) => {
        this.isReportLoading = false;
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `platana_report_${this.selectedProduct!.id}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      },
      error: () => {
        this.isReportLoading = false;
        this.saveResult = { success: false, message: this.translation.t('dashboard.reportError') };
      }
    });
  }

  deleteProduct() {
    if (!this.selectedProduct) return;
    if (!confirm(this.translation.tWith('dashboard.deleteConfirm', { name: `${this.selectedProduct.brand} ${this.selectedProduct.model}` }))) return;
    this.isDeleting = true;
    this.api.deleteProduct(this.selectedProduct.id).subscribe({
      next: () => {
        this.isDeleting = false;
        this.allProducts = this.allProducts.filter(p => p.id !== this.selectedProduct!.id);
        this.closeDetail();
      },
      error: (err) => {
        this.isDeleting = false;
        this.saveResult = { success: false, message: err?.error?.detail || this.translation.t('dashboard.deleteError') };
      }
    });
  }
}
