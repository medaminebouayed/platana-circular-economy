import { Component, OnInit } from '@angular/core';

interface Workshop {
  id: string;
  name: string;
  city: string;
  region: string;
  capacity: number;
  occupancy: number;
  avgCost: number;
  distance: number;
  specialties: string[];
  status: 'available' | 'busy' | 'full';
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

@Component({
  selector: 'app-logistics',
  templateUrl: './logistics.component.html',
  styleUrls: ['./logistics.component.css']
})
export class LogisticsComponent implements OnInit {

  workshops: Workshop[] = [
    {
      id: 'W01', name: 'Atelier Platana Nord',
      city: 'Lille', region: 'Hauts-de-France',
      capacity: 200, occupancy: 62, avgCost: 48,
      distance: 230, specialties: ['Smartphone', 'Ordinateur', 'Tablette'],
      status: 'available'
    },
    {
      id: 'W02', name: 'Centre Reconditionnement Est',
      city: 'Strasbourg', region: 'Grand Est',
      capacity: 350, occupancy: 87, avgCost: 52,
      distance: 490, specialties: ['TV', 'Electroménager', 'Outillage'],
      status: 'busy'
    },
    {
      id: 'W03', name: 'Hub Reconditionnement Sud',
      city: 'Lyon', region: 'Auvergne-Rhône-Alpes',
      capacity: 280, occupancy: 45, avgCost: 44,
      distance: 460, specialties: ['Smartphone', 'Audio', 'Console de jeux'],
      status: 'available'
    },
    {
      id: 'W04', name: 'Site Atlantique',
      city: 'Nantes', region: 'Pays de la Loire',
      capacity: 180, occupancy: 95, avgCost: 58,
      distance: 380, specialties: ['Aspirateur', 'Electroménager'],
      status: 'full'
    },
  ];

  allocations: AllocationDecision[] = [
    { productId: 'PLT-92301', productName: 'Samsung Galaxy S22', grade: 'B', decision: 'RESALE_DIRECT', channel: 'BackMarket', estimatedDelay: 2, transportCost: 12, totalCost: 12 },
    { productId: 'PLT-92274', productName: 'Dyson V11 Absolute', grade: 'C', decision: 'RECONDITION', workshop: 'Atelier Platana Nord', channel: 'Leboncoin', estimatedDelay: 7, transportCost: 18, totalCost: 66 },
    { productId: 'PLT-92231', productName: 'Kärcher K5 Premium', grade: 'D', decision: 'RECYCLE', channel: 'Filière D3E', estimatedDelay: 5, transportCost: 22, totalCost: 22 },
    { productId: 'PLT-92265', productName: 'iPad Pro 11" 2022', grade: 'B', decision: 'RESALE_DIRECT', channel: 'BackMarket', estimatedDelay: 2, transportCost: 8, totalCost: 8 },
    { productId: 'PLT-92254', productName: 'Sony WH-1000XM5', grade: 'A', decision: 'RESALE_DIRECT', channel: 'Platana Store', estimatedDelay: 1, transportCost: 5, totalCost: 5 },
    { productId: 'PLT-92243', productName: 'Dell XPS 15 Laptop', grade: 'C', decision: 'RECONDITION', workshop: 'Hub Reconditionnement Sud', channel: 'eBay', estimatedDelay: 10, transportCost: 25, totalCost: 69 },
  ];

  globalStats = {
    totalPending: 38,
    forRecondition: 14,
    forResale: 18,
    forRecycle: 6,
    avgDelay: 4.5,
    totalTransportCost: 1248,
  };

  selectedWorkshop: Workshop | null = null;
  isOptimizing = false;
  optimizationDone = false;
  Math = Math; // expose Math to template


  ngOnInit() {}

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
    setTimeout(() => {
      this.isOptimizing = false;
      this.optimizationDone = true;
    }, 2500);
  }

  selectWorkshop(w: Workshop) {
    this.selectedWorkshop = this.selectedWorkshop?.id === w.id ? null : w;
  }
}
