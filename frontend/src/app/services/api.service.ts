import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, of, throwError } from 'rxjs';
import { catchError, map, tap } from 'rxjs/operators';

// Schemas match backend specifications in schemas.py
export interface GradingResponse {
  product_id?: string;
  grade: string;
  grade_confidence: number;
  grade_probabilities: { [key: string]: number };
  detected_defects: Array<{ type: string; probability: number; box?: [number, number, number, number] }>;
  attention_weights?: number[];
  num_views_used: number;
  processing_time_ms: number;
}

export interface PricingRequest {
  grade: string;
  category: string;
  brand: string;
  model: string;
  original_price: number;
  age_days: number;
  repair_cost?: number;
  season?: string;
}

export interface PricingResponse {
  predicted_price: number;
  confidence_interval: [number, number];
  price_ratio: number;
  explanation: string;
}

export interface ProductSheetResponse {
  product_id: string;
  title: string;
  description: string;
  highlights: string[];
  attention_points: string[];
  recommended_channels: string[];
  decision: 'RECONDITION' | 'RESALE_DIRECT' | 'RECYCLE' | 'HOLD';
  decision_rationale: string;
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private cvUrl = 'http://localhost:8001';
  private pricingUrl = 'http://localhost:8002';
  private orchestratorUrl = 'http://localhost:8000';

  // Toggle for simulation mode
  public isSimulationMode = true;

  constructor(private http: HttpClient) {
    // Detect if we have backend running
    this.checkBackends();
  }

  private checkBackends() {
    this.http.get(`${this.cvUrl}/health`).pipe(
      tap(() => {
        console.log('[API] CV Service detected, disabling simulation mode.');
        this.isSimulationMode = false;
      }),
      catchError(() => {
        console.log('[API] CV Service offline, using simulation mode.');
        return of(null);
      })
    ).subscribe();
  }

  // --- CV SERVICE ---
  gradeProduct(files: File[], productId?: string): Observable<GradingResponse> {
    if (this.isSimulationMode) {
      // Simulate network lag
      return new Observable<GradingResponse>(observer => {
        setTimeout(() => {
          const mockResponse = this.generateMockGrading(files, productId);
          observer.next(mockResponse);
          observer.complete();
        }, 1500);
      });
    }

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file, file.name);
    });
    if (productId) {
      formData.append('product_id', productId);
    }

    return this.http.post<GradingResponse>(`${this.cvUrl}/grade`, formData).pipe(
      catchError(err => {
        console.warn('Real CV backend failed, falling back to mock simulator:', err);
        return of(this.generateMockGrading(files, productId));
      })
    );
  }

  // --- PRICING SERVICE ---
  predictPrice(request: PricingRequest): Observable<PricingResponse> {
    if (this.isSimulationMode) {
      return new Observable<PricingResponse>(observer => {
        setTimeout(() => {
          observer.next(this.calculateMockPrice(request));
          observer.complete();
        }, 800);
      });
    }

    return this.http.post<PricingResponse>(`${this.pricingUrl}/predict`, request).pipe(
      catchError(err => {
        console.warn('Real pricing backend failed, falling back to mock simulator:', err);
        return of(this.calculateMockPrice(request));
      })
    );
  }

  // --- PRODUCT SHEET GENERATOR (GenAI) ---
  generateProductSheet(productData: any): Observable<ProductSheetResponse> {
    return new Observable<ProductSheetResponse>(observer => {
      setTimeout(() => {
        const brand = productData.brand || 'Générique';
        const model = productData.model || 'Modèle';
        const category = productData.category || 'Électronique';
        const grade = productData.grade || 'B';
        const defects = productData.defects || [];
        const price = productData.predictedPrice || 250;

        const gradeLabels: { [key: string]: string } = {
          'A': 'Excellent État',
          'B': 'Très Bon État',
          'C': 'État Correct',
          'D': 'À reconditionner'
        };

        const title = `${brand} ${model} - ${gradeLabels[grade]} (${category})`;
        const defectText = defects.length > 0
          ? `Présente des traces d'usure légères : ${defects.join(', ')}.`
          : `Aucun défaut esthétique majeur détecté.`;

        const description = `Ce produit ${brand} ${model} a été rigoureusement inspecté par nos algorithmes de vision par ordinateur Platana. Classé en grade ${grade} (${gradeLabels[grade]}), il est fonctionnel à 100%. ${defectText} Idéal pour une démarche éco-responsable, ce produit reconditionné évite l'extraction de matières premières et la mise en décharge de déchets électroniques tout en offrant un prix attractif de ${price}€ (comparé à son prix d'origine).`;

        const highlights = [
          'Testé et validé par notre laboratoire de grading multi-vues',
          'Fonctionnalités internes vérifiées à 100%',
          'Nettoyage antibactérien complet effectué',
          'Emballage éco-conçu avec accessoires compatibles inclus',
          'Garantie légale de 12 mois Platana'
        ];

        const attentionPoints = defects.map((d: string) => {
          if (d === 'scratch') return 'Rayures légères visibles sur la face arrière';
          if (d === 'dent') return 'Léger impact sur le châssis';
          if (d === 'discoloration') return 'Légère décoloration sur les tranches';
          return `Défaut esthétique de type: ${d}`;
        });

        if (attentionPoints.length === 0) {
          attentionPoints.push('Aucun point d\'attention critique à signaler');
        }

        // Decision logic
        let decision: 'RECONDITION' | 'RESALE_DIRECT' | 'RECYCLE' | 'HOLD' = 'RESALE_DIRECT';
        let decisionRationale = 'Le produit est dans un état esthétique excellent ne nécessitant aucune intervention technique.';
        let channels = ['BackMarket', 'Leboncoin', 'Platana Store'];

        if (grade === 'C' || grade === 'D') {
          const cost = productData.repairCost || 0;
          const original = productData.originalPrice || 500;
          if (cost > original * 0.5) {
            decision = 'RECYCLE';
            decisionRationale = `Les coûts de reconditionnement (${cost}€) dépassent 50% du prix d'origine (${original}€). Le recyclage matière est économiquement et écologiquement recommandé.`;
            channels = ['Filière D3E locale', 'Recyclage Platana'];
          } else {
            decision = 'RECONDITION';
            decisionRationale = `Le grade de départ est bas (${grade}), mais le coût de réparation (${cost}€) reste rentable par rapport au prix estimé. Remise en état conseillée avant publication.`;
            channels = ['BackMarket', 'eBay', 'Vente Privée Reconditionné'];
          }
        }

        observer.next({
          product_id: productData.productId || 'PLT-' + Math.floor(Math.random() * 90000 + 10000),
          title,
          description,
          highlights,
          attention_points: attentionPoints,
          recommended_channels: channels,
          decision,
          decision_rationale: decisionRationale
        });
        observer.complete();
      }, 2000);
    });
  }

  // --- MOCK SIMULATORS ---
  private generateMockGrading(files: File[], productId?: string): GradingResponse {
    const fileName = files[0]?.name.toLowerCase() || 'iphone.jpg';
    
    let grade = 'B';
    let confidence = 0.88;
    let detected_defects: Array<{ type: string; probability: number; box?: [number, number, number, number] }> = [];
    let probs = { 'A': 0.15, 'B': 0.70, 'C': 0.12, 'D': 0.03 };

    if (fileName.includes('broken') || fileName.includes('crack') || fileName.includes('casse')) {
      grade = 'D';
      confidence = 0.94;
      detected_defects = [
        { type: 'crack', probability: 0.92, box: [20, 30, 80, 75] },
        { type: 'scratch', probability: 0.85, box: [10, 15, 40, 50] }
      ];
      probs = { 'A': 0.01, 'B': 0.03, 'C': 0.08, 'D': 0.88 };
    } else if (fileName.includes('scratch') || fileName.includes('rayure')) {
      grade = 'C';
      confidence = 0.82;
      detected_defects = [
        { type: 'scratch', probability: 0.78, box: [50, 45, 90, 80] }
      ];
      probs = { 'A': 0.08, 'B': 0.22, 'C': 0.65, 'D': 0.05 };
    } else if (fileName.includes('clean') || fileName.includes('neuf') || fileName.includes('perfect')) {
      grade = 'A';
      confidence = 0.96;
      detected_defects = [];
      probs = { 'A': 0.92, 'B': 0.06, 'C': 0.01, 'D': 0.01 };
    } else {
      // Random defect generator
      const rand = Math.random();
      if (rand > 0.6) {
        detected_defects = [
          { type: 'scratch', probability: 0.72, box: [40, 20, 60, 60] }
        ];
        grade = 'B';
        probs = { 'A': 0.10, 'B': 0.75, 'C': 0.12, 'D': 0.03 };
      } else if (rand < 0.2) {
        detected_defects = [
          { type: 'dent', probability: 0.82, box: [15, 60, 35, 80] },
          { type: 'discoloration', probability: 0.61, box: [5, 5, 25, 25] }
        ];
        grade = 'C';
        probs = { 'A': 0.02, 'B': 0.18, 'C': 0.72, 'D': 0.08 };
      }
    }

    return {
      product_id: productId || 'PLT-' + Math.floor(Math.random() * 90000 + 10000),
      grade,
      grade_confidence: confidence,
      grade_probabilities: probs,
      detected_defects,
      attention_weights: Array.from({ length: files.length }, () => Math.random()),
      num_views_used: files.length,
      processing_time_ms: Math.floor(Math.random() * 200 + 180)
    };
  }

  private calculateMockPrice(request: PricingRequest): PricingResponse {
    const basePrices: { [key: string]: number } = {
      'A': 0.80,
      'B': 0.68,
      'C': 0.52,
      'D': 0.35
    };

    const gradeFactor = basePrices[request.grade] || 0.60;
    
    // Linear aging model (loses value over time, cap at max 60% loss from age)
    const ageLossRatio = Math.min(request.age_days * 0.0004, 0.60);
    
    // Base predicted price
    let predicted = request.original_price * gradeFactor * (1 - ageLossRatio);
    
    // Subtract repair cost with 1.2x penalty (reconditioned overhead)
    const repairCost = request.repair_cost || 0;
    predicted = Math.max(predicted - (repairCost * 1.15), request.original_price * 0.1);

    // Apply seasonal adjustments
    let explanation = `Estimation de pricing pour ${request.brand} ${request.model} en grade ${request.grade}`;
    if (request.season === 'summer') {
      predicted *= 0.95;
      explanation += '. Ajustement de -5% appliqué pour la saison creuse estivale.';
    } else if (request.season === 'winter') {
      predicted *= 1.05;
      explanation += '. Ajustement de +5% appliqué pour la période des fêtes hivernales.';
    } else {
      explanation += `. Modèle de décote linéaire appliqué pour l'âge de ${request.age_days} jours.`;
    }

    predicted = Math.round(predicted * 100) / 100;
    const intervalMin = Math.round(predicted * 0.92 * 100) / 100;
    const intervalMax = Math.round(predicted * 1.08 * 100) / 100;
    const ratio = Math.round((predicted / request.original_price) * 100) / 100;

    explanation += ` Rentabilité estimée après déduction de ${repairCost}€ de frais de remise en état.`;

    return {
      predicted_price: predicted,
      confidence_interval: [intervalMin, intervalMax],
      price_ratio: ratio,
      explanation
    };
  }
}
