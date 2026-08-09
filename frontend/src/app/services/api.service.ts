import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ProductSummary {
  id: string;
  brand: string;
  model: string;
  year: number;
  original_price: number;
  status: string;
  image_paths?: string[];
  ai_predictions?: {
    grade: string;
    defects: string[];
    market_price: number;
    refurb_cost: number;
    profit: number;
    decision: string;
    title: string;
    description: string;
  };
  admin_review?: {
    grade: string;
    market_price: number;
    title: string;
    description: string;
    defects: string[];
    refurb_cost: number;
    reviewed_by: string;
  };
  shopify_url?: string;
}

export interface UploadEvaluatePayload {
  brand: string;
  model: string;
  year: number;
  original_price: number;
  user_email: string;
  files: File[];
}

export interface AdminReviewPayload {
  grade: string;
  defects: string[];
  market_price: number;
  refurb_cost: number;
  title: string;
  description: string;
  reviewed_by: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {

  constructor(private http: HttpClient) {}

  // ─── PRODUCTS ─────────────────────────────────────────────
  uploadAndEvaluate(payload: UploadEvaluatePayload): Observable<any> {
    const form = new FormData();
    form.append('brand', payload.brand);
    form.append('model', payload.model);
    form.append('year', String(payload.year));
    form.append('original_price', String(payload.original_price));
    form.append('user_email', payload.user_email);
    payload.files.forEach(f => form.append('files', f));
    return this.http.post<any>('/api/products/upload', form);
  }

  getPendingProducts(): Observable<ProductSummary[]> {
    return this.http.get<ProductSummary[]>('/api/products/pending');
  }

  getAllProducts(): Observable<ProductSummary[]> {
    return this.http.get<ProductSummary[]>('/api/products');
  }

  getUserProducts(email: string): Observable<ProductSummary[]> {
    return this.http.get<ProductSummary[]>(`/api/products/user/${email}`);
  }

  reviewProduct(productId: string, review: AdminReviewPayload): Observable<any> {
    return this.http.patch<any>(`/api/products/${productId}/review`, review);
  }

  rejectProduct(productId: string, reason: string = "Rejeté par l'administrateur"): Observable<any> {
    return this.http.post<any>(`/api/products/${productId}/reject`, { reason });
  }

  reEvaluateProduct(productId: string): Observable<any> {
    return this.http.post<any>(`/api/products/${productId}/re-evaluate`, {});
  }

  publishProduct(productId: string): Observable<any> {
    return this.http.post<any>(`/api/products/${productId}/publish`, {});
  }

  updatePreferences(prefs: any): Observable<any> {
    return this.http.put<any>('/api/auth/preferences', prefs);
  }

  getMe(): Observable<any> {
    return this.http.get<any>('/api/auth/me');
  }

  // ─── DASHBOARD & LOGISTICS ────────────────────────────────
  getDashboardStats(): Observable<any> {
    return this.http.get<any>('/api/stats/dashboard');
  }

  getWorkshops(): Observable<any[]> {
    return this.http.get<any[]>('/api/logistics/workshops');
  }

  createWorkshop(workshop: any): Observable<any> {
    return this.http.post<any>('/api/logistics/workshops', workshop);
  }

  updateWorkshop(id: string, workshop: any): Observable<any> {
    return this.http.put<any>(`/api/logistics/workshops/${id}`, workshop);
  }

  deleteWorkshop(id: string): Observable<any> {
    return this.http.delete<any>(`/api/logistics/workshops/${id}`);
  }

  optimizeLogistics(): Observable<any> {
    return this.http.post<any>('/api/logistics/optimize', {});
  }
}

