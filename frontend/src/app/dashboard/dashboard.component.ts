import { Component, OnInit } from '@angular/core';
import { AuthService } from '../services/auth.service';

interface KpiCard {
  label: string;
  value: string;
  unit: string;
  change: number;
  icon: string;
  color: string;
}

interface RecentProduct {
  id: string;
  name: string;
  grade: string;
  category: string;
  price: number;
  status: 'recondition' | 'resale' | 'recycle' | 'pending';
  date: string;
}

interface ChannelData {
  channel: string;
  products: number;
  revenue: number;
  pct: number;
}

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit {
  
  kpis: KpiCard[] = [
    { label: 'Produits valorisés', value: '1 247', unit: 'ce mois', change: +12.4, icon: 'recycle', color: 'green' },
    { label: 'Revenu revente', value: '89 430', unit: '€ / mois', change: +8.7, icon: 'euro', color: 'blue' },
    { label: 'Produits détruits évités', value: '94.2', unit: '%', change: +3.1, icon: 'leaf', color: 'emerald' },
    { label: 'Écart Pricing Moyen', value: '5.8', unit: '% vs réel', change: -1.2, icon: 'target', color: 'purple' },
    { label: 'Temps de traitement moyen', value: '2.4', unit: 's / produit', change: -0.3, icon: 'zap', color: 'yellow' },
    { label: 'Produits en attente', value: '38', unit: 'à processer', change: +5, icon: 'clock', color: 'orange' },
  ];

  recentProducts: RecentProduct[] = [
    { id: 'PLT-92301', name: 'Samsung Galaxy S22', grade: 'B', category: 'Smartphone', price: 349, status: 'resale', date: 'Aujourd\'hui 14:22' },
    { id: 'PLT-92289', name: 'Apple MacBook Air M1', grade: 'A', category: 'Ordinateur', price: 780, status: 'resale', date: 'Aujourd\'hui 13:05' },
    { id: 'PLT-92274', name: 'Dyson V11 Absolute', grade: 'C', category: 'Aspirateur', price: 189, status: 'recondition', date: 'Aujourd\'hui 11:48' },
    { id: 'PLT-92261', name: 'iPad Pro 11" 2022', grade: 'B', category: 'Tablette', price: 510, status: 'resale', date: 'Hier 17:30' },
    { id: 'PLT-92249', name: 'Sony WH-1000XM5', grade: 'A', category: 'Audio', price: 198, status: 'resale', date: 'Hier 16:15' },
    { id: 'PLT-92231', name: 'Kärcher K5 Premium', grade: 'D', category: 'Outillage', price: 0, status: 'recycle', date: 'Hier 09:00' },
    { id: 'PLT-92218', name: 'LG OLED C2 55"', grade: 'B', category: 'TV', price: 640, status: 'resale', date: '26/07 18:11' },
    { id: 'PLT-92205', name: 'iPhone 13 Pro', grade: 'A', category: 'Smartphone', price: 560, status: 'resale', date: '26/07 14:52' },
  ];

  channelData: ChannelData[] = [
    { channel: 'BackMarket', products: 418, revenue: 38200, pct: 42 },
    { channel: 'Leboncoin', products: 286, revenue: 21900, pct: 29 },
    { channel: 'Platana Store', products: 197, revenue: 18100, pct: 20 },
    { channel: 'eBay', products: 97, revenue: 11230, pct: 9 },
  ];

  gradeDistribution = [
    { grade: 'A', count: 312, color: '#10b981' },
    { grade: 'B', count: 544, color: '#0ea5e9' },
    { grade: 'C', count: 267, color: '#f59e0b' },
    { grade: 'D', count: 124, color: '#ef4444' },
  ];

  totalProducts = 1247;

  monthlyTrend = [
    { month: 'Fév', valorises: 890, detruits: 210 },
    { month: 'Mar', valorises: 940, detruits: 180 },
    { month: 'Avr', valorises: 1010, detruits: 155 },
    { month: 'Mai', valorises: 1080, detruits: 130 },
    { month: 'Jun', valorises: 1150, detruits: 118 },
    { month: 'Jul', valorises: 1247, detruits: 72 },
  ];

  maxMonthlyTotal = 0;

  constructor(public authService: AuthService) {}

  ngOnInit() {
    this.maxMonthlyTotal = Math.max(...this.monthlyTrend.map(m => m.valorises + m.detruits));
  }

  getStatusBadgeClass(status: string): string {
    switch (status) {
      case 'resale': return 'badge badge-success';
      case 'recondition': return 'badge badge-warning';
      case 'recycle': return 'badge badge-danger';
      case 'pending': return 'badge badge-info';
      default: return 'badge';
    }
  }

  getStatusLabel(status: string): string {
    switch (status) {
      case 'resale': return 'Revente directe';
      case 'recondition': return 'À reconditionner';
      case 'recycle': return 'Recyclage D3E';
      case 'pending': return 'En analyse';
      default: return status;
    }
  }

  getGradeBadgeClass(grade: string): string {
    switch (grade) {
      case 'A': return 'grade-badge grade-a';
      case 'B': return 'grade-badge grade-b';
      case 'C': return 'grade-badge grade-c';
      case 'D': return 'grade-badge grade-d';
      default: return 'grade-badge';
    }
  }

  getBarHeight(month: any): number {
    return ((month.valorises + month.detruits) / this.maxMonthlyTotal) * 100;
  }

  getGradePct(count: number): number {
    return Math.round((count / this.totalProducts) * 100);
  }
}
