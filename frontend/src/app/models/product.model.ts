// Ce que l'API FastAPI renvoie après l'upload et l'évaluation de l'IA
export interface AIPredictions {
    grade: string;
    defects: string[];
    market_price: number;
    refurb_cost: number;
    profit: number;
    decision: string;
    title: string;
    description: string;
}

// La réponse complète de l'endpoint /upload
export interface EvaluationResponse {
    product_id: string;
    status: string;
    ai_predictions: AIPredictions;
}

// Ce que Angular envoie à FastAPI quand l'admin valide (endpoint /review)
export interface AdminReviewPayload {
    grade: string;
    defects: string[];
    market_price: number;
    refurb_cost: number;
    title: string;
    description: string;
}

// La réponse de l'endpoint /publish
export interface PublishResponse {
    status: string;
    shopify_url: string;
}