import { Component, OnInit } from '@angular/core';
import { ApiService } from '../services/api.service';
import { AuthService } from '../services/auth.service';

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

  activeTab: 'submit' | 'history' = 'submit';
  userProducts: any[] = [];
  isLoadingHistory = false;

  constructor(private api: ApiService, public authService: AuthService) {}

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
      { label: 'Upload des images vers le serveur', status: 'running' },
      { label: 'Analyse visuelle IA (Vision CV)', status: 'pending' },
      { label: 'Estimation du prix de revente (ML)', status: 'pending' },
      { label: 'Génération de la fiche produit (GenAI)', status: 'pending' },
      { label: 'Envoi à l\'équipe de validation', status: 'pending' },
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
        this.errorMessage = err?.error?.detail || 'Le serveur est injoignable ou une erreur inattendue est survenue.';
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
      RESALE_DIRECT: '✅ Revente directe recommandée',
      RECONDITION: '🔧 Reconditionnement requis',
      RECYCLE: '♻️ Recyclage recommandé',
    };
    return map[decision] || decision;
  }
}
