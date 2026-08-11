import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { EvaluationResponse, AdminReviewPayload, PublishResponse } from '../models/product.model';

@Injectable({
    providedIn: 'root'
})
export class ProductService {

    private apiUrl = '/api/products';

    constructor(private http: HttpClient) { }

    /**
     * Étape 1 : Upload des images et infos vers FastAPI
     */
    uploadAndEvaluate(brand: string, model: string, year: number, price: number, files: File[]): Observable<EvaluationResponse> {
        const formData = new FormData();
        formData.append('brand', brand);
        formData.append('model', model);
        formData.append('year', year.toString());
        formData.append('original_price', price.toString());

        files.forEach(file => formData.append('files', file, file.name));

        return this.http.post<EvaluationResponse>(`${this.apiUrl}/upload`, formData).pipe(
            catchError(this.handleError('Upload et Évaluation'))
        );
    }

    /**
     * Étape 2 : Envoi des corrections de l'admin au Backend (FastAPI sauvegardera en DB)
     */
    submitAdminReview(productId: string, payload: AdminReviewPayload): Observable<any> {
        const headers = new HttpHeaders({ 'Content-Type': 'application/json' });
        return this.http.patch(`${this.apiUrl}/${productId}/review`, payload, { headers }).pipe(
            catchError(this.handleError('Validation Admin'))
        );
    }

    /**
     * Étape 3 : Demande de publication au Backend (FastAPI appellera Dify puis Shopify)
     */
    publishProduct(productId: string): Observable<PublishResponse> {
        return this.http.post<PublishResponse>(`${this.apiUrl}/${productId}/publish`, {}).pipe(
            catchError(this.handleError('Publication Shopify'))
        );
    }

    private handleError(operation: string) {
        return (error: HttpErrorResponse) => {
            console.error(`Erreur lors de ${operation}`, error);
            let errorMsg = `Une erreur est survenue pendant ${operation}.`;
            if (error.error && error.error.detail) {
                errorMsg = error.error.detail; // Récupère le message d'erreur de FastAPI
            }
            return throwError(() => new Error(errorMsg));
        };
    }
}