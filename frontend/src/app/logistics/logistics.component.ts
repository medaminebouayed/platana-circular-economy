import { Component, OnInit } from '@angular/core';
import { ApiService } from '../services/api.service';

interface Workshop {
  id: string;
  name: string;
  city: string;
  region: string;
  capacity: number;
  occupancy: number;
  avg_cost: number;
  distance: number;
  specialties: string[];
  status: 'available' | 'busy' | 'full';
  min_profit_threshold: number;
  max_items_per_batch: number;
}

interface AllocationDecision {
  productId: string;
  productName: string;
  grade: string;
  decision: 'RECONDITION' | 'RESALE_DIRECT' | 'RECYCLE';
  workshop?: string;
  channel: string;
  estimatedDelay: number;
  transportCost: number;
  totalCost: number;
}

const EMPTY_WORKSHOP: Partial<Workshop> = {
  name: '', city: '', region: '', capacity: 100,
  occupancy: 0, avg_cost: 30, distance: 200,
  specialties: [], status: 'available',
  min_profit_threshold: 20, max_items_per_batch: 10
};

@Component({
  selector: 'app-logistics',
  templateUrl: './logistics.component.html',
  styleUrls: ['./logistics.component.css']
})
export class LogisticsComponent implements OnInit {

  workshops: Workshop[] = [];
  allocations: AllocationDecision[] = [];
  totalOptimizationProfit = 0;

  globalStats = {
    totalPending: 0,
    forRecondition: 0,
    forResale: 0,
    forRecycle: 0,
    avgDelay: 0,
    totalTransportCost: 0,
  };

  selectedWorkshop: Workshop | null = null;
  isOptimizing = false;
  optimizationDone = false;
  optimizationStatus = '';
  Math = Math;

  // Admin CRUD state
  showWorkshopModal = false;
  isEditMode = false;
  editingWorkshop: any = { ...EMPTY_WORKSHOP };
  isSavingWorkshop = false;
  workshopSpecialtiesInput = '';

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadWorkshops();
    this.api.getDashboardStats().subscribe(stats => this.globalStats = stats);
  }

  loadWorkshops() {
    this.api.getWorkshops().subscribe(ws => this.workshops = ws);
  }

  getOccupancyColor(pct: number): string {
    if (pct < 60) return '#10b981';
    if (pct < 85) return '#f59e0b';
    return '#ef4444';
  }

  getStatusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      available: 'badge badge-success',
      busy: 'badge badge-warning',
      full: 'badge badge-danger',
    };
    return map[status] || 'badge';
  }

  getStatusLabel(status: string): string {
    const map: Record<string, string> = {
      available: 'Disponible',
      busy: 'Chargé',
      full: 'Complet',
    };
    return map[status] || status;
  }

  getDecisionClass(d: string): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: 'badge badge-success',
      RECONDITION: 'badge badge-warning',
      RECYCLE: 'badge badge-danger',
    };
    return map[d] || 'badge';
  }

  getDecisionLabel(d: string): string {
    const map: Record<string, string> = {
      RESALE_DIRECT: 'Revente directe',
      RECONDITION: 'Reconditionnement',
      RECYCLE: 'Recyclage',
    };
    return map[d] || d;
  }

  runOptimization() {
    this.isOptimizing = true;
    this.optimizationDone = false;
    this.api.optimizeLogistics().subscribe({
      next: (res) => {
        this.allocations = res.allocations || [];
        this.totalOptimizationProfit = res.total_profit || 0;
        this.optimizationStatus = res.status || '';
        this.isOptimizing = false;
        this.optimizationDone = true;
      },
      error: (err) => {
        this.isOptimizing = false;
        const detail = err?.error?.detail || 'Optimization failed. Is the orchestrator running?';
        alert(detail);
      }
    });
  }

  selectWorkshop(w: Workshop) {
    this.selectedWorkshop = this.selectedWorkshop?.id === w.id ? null : w;
  }

  // ── Admin CRUD ──────────────────────────────────────────────
  openAddModal() {
    this.isEditMode = false;
    this.editingWorkshop = { ...EMPTY_WORKSHOP };
    this.workshopSpecialtiesInput = '';
    this.showWorkshopModal = true;
  }

  openEditModal(w: Workshop, event: Event) {
    event.stopPropagation();
    this.isEditMode = true;
    this.editingWorkshop = { ...w };
    this.workshopSpecialtiesInput = (w.specialties || []).join(', ');
    this.showWorkshopModal = true;
  }

  closeModal() {
    this.showWorkshopModal = false;
  }

  saveWorkshop() {
    this.isSavingWorkshop = true;
    const payload = {
      ...this.editingWorkshop,
      specialties: this.workshopSpecialtiesInput
        .split(',')
        .map((s: string) => s.trim())
        .filter((s: string) => s.length > 0)
    };

    if (this.isEditMode && payload.id) {
      const id = payload.id;
      delete payload.id;
      this.api.updateWorkshop(id, payload).subscribe({
        next: () => { this.isSavingWorkshop = false; this.closeModal(); this.loadWorkshops(); },
        error: () => { this.isSavingWorkshop = false; alert('Erreur lors de la mise à jour.'); }
      });
    } else {
      delete payload.id;
      this.api.createWorkshop(payload).subscribe({
        next: () => { this.isSavingWorkshop = false; this.closeModal(); this.loadWorkshops(); },
        error: () => { this.isSavingWorkshop = false; alert('Erreur lors de la création.'); }
      });
    }
  }

  deleteWorkshop(w: Workshop, event: Event) {
    event.stopPropagation();
    if (!confirm(`Supprimer l'atelier "${w.name}" ?`)) return;
    this.api.deleteWorkshop(w.id).subscribe({
      next: () => { this.loadWorkshops(); if (this.selectedWorkshop?.id === w.id) this.selectedWorkshop = null; },
      error: () => alert('Erreur lors de la suppression.')
    });
  }
}
