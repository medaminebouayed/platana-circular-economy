import { Component, OnInit } from '@angular/core';
import { AuthService } from '../services/auth.service';
import { ApiService, ProductSummary } from '../services/api.service';

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
  isSaving = false;
  isPublishing = false;
  saveResult: { success: boolean; message: string } | null = null;
  publishResult: { success: boolean; message: string; url?: string } | null = null;

  kpis = [
    { label: 'En attente de validation', value: '0', color: 'blue' },
    { label: 'Publiés', value: '0', color: 'green' },
    { label: 'Rejetés', value: '0', color: 'red' },
    { label: 'Total traités', value: '0', color: 'purple' },
  ];

  constructor(public authService: AuthService, private api: ApiService) {}

  ngOnInit() { this.loadProducts(); }

  loadProducts() {
    this.isLoading = true;
    this.api.getAllProducts().subscribe({
      next: (products) => {
        this.allProducts = products;
        this.api.getDashboardStats().subscribe(stats => {
          this.kpis[0].value = stats.totalPending.toString();
          this.kpis[1].value = products.filter(p => p.status === 'PUBLISHED').length.toString();
          this.kpis[2].value = products.filter(p => p.status === 'REJECTED').length.toString();
          this.kpis[3].value = (products.length).toString(); // Total processed
          this.isLoading = false;
        });
      },
      error: () => { this.isLoading = false; }
    });
  }

  get pendingProducts(): ProductSummary[] {
    return this.allProducts.filter(p => p.status === 'PENDING_ADMIN_REVIEW');
  }

  get publishedProducts(): ProductSummary[] {
    return this.allProducts.filter(p => p.status === 'PUBLISHED');
  }

  selectProduct(product: ProductSummary) {
    this.selectedProduct = product;
    const ai = product.ai_predictions;
    const review = product.admin_review;
    this.adminGrade = review?.grade || ai?.grade || 'B';
    this.adminPrice = review?.market_price || ai?.market_price || 0;
    this.adminTitle = review?.title || ai?.title || '';
    this.adminDescription = review?.description || ai?.description || '';
    this.adminRefurbCost = review?.refurb_cost || ai?.refurb_cost || 0;
    this.saveResult = null;
    this.publishResult = null;
  }

  closeDetail() { this.selectedProduct = null; this.saveResult = null; this.publishResult = null; }

  saveReview() {
    if (!this.selectedProduct) return;
    this.isSaving = true;
    const reviewPayload = {
      grade: this.adminGrade,
      defects: this.selectedProduct.ai_predictions?.defects || [],
      market_price: this.adminPrice,
      refurb_cost: this.adminRefurbCost,
      title: this.adminTitle,
      description: this.adminDescription,
      reviewed_by: this.authService.currentUserValue?.email || 'admin'
    };
    this.api.reviewProduct(this.selectedProduct.id, reviewPayload).subscribe({
      next: () => {
        this.isSaving = false;
        this.saveResult = { success: true, message: 'Modifications enregistrées. Le produit est prêt pour publication.' };
        this.loadProducts();
      },
      error: () => {
        this.isSaving = false;
        this.saveResult = { success: false, message: 'Erreur lors de la sauvegarde.' };
      }
    });
  }

  isRejecting = false;
  isReEvaluating = false;

  rejectProduct() {
    if (!this.selectedProduct) return;
    if (!confirm(`Êtes-vous sûr de vouloir refuser le produit ${this.selectedProduct.brand} ${this.selectedProduct.model} ?`)) return;
    this.isRejecting = true;
    this.api.rejectProduct(this.selectedProduct.id).subscribe({
      next: () => {
        this.isRejecting = false;
        this.saveResult = { success: true, message: 'Le produit a été refusé et marqué comme rejeté.' };
        if (this.selectedProduct) this.selectedProduct.status = 'REJECTED';
        this.loadProducts();
      },
      error: (err) => {
        this.isRejecting = false;
        this.saveResult = { success: false, message: err?.error?.detail || 'Erreur lors du rejet du produit.' };
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
        this.saveResult = { success: true, message: 'Ré-évaluation effectuée par Dify AI avec succès.' };
        if (this.selectedProduct) {
          this.selectedProduct.status = 'PENDING_ADMIN_REVIEW';
          this.selectedProduct.ai_predictions = res.ai_predictions;
          this.selectProduct(this.selectedProduct);
        }
        this.loadProducts();
      },
      error: (err) => {
        this.isReEvaluating = false;
        this.saveResult = { success: false, message: err?.error?.detail || 'Échec de la ré-évaluation.' };
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
        this.publishResult = { success: true, message: 'Produit publié avec succès !', url: res.shopify_url };
        this.loadProducts();
      },
      error: (err) => {
        this.isPublishing = false;
        const detail = err?.error?.detail || 'Erreur de publication.';
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
      PENDING_EVALUATION: 'En analyse IA',
      PENDING_ADMIN_REVIEW: 'Attente validation',
      REVIEWED: 'Révisé',
      PUBLISHED: 'Publié',
      REJECTED: 'Rejeté',
      AI_ERROR: 'Erreur IA',
    };
    return map[status] || status;
  }

  getDecisionLabel(decision?: string): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: '✅ Revente directe',
      RECONDITION: '🔧 Reconditionnement',
      RECYCLE: '♻️ Recyclage',
    };
    return decision ? (map[decision] || decision) : '—';
  }
}
