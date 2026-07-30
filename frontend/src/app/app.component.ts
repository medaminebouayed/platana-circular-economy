import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { AuthService, User } from './services/auth.service';
import { ApiService } from './services/api.service';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  currentUser: User | null = null;
  currentRoute = '';
  mobileMenuOpen = false;

  constructor(
    public authService: AuthService,
    public apiService: ApiService,
    private router: Router
  ) {}

  ngOnInit() {
    this.authService.currentUser$.subscribe(user => {
      this.currentUser = user;
    });

    // Track active route changes for active class highlighting
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: any) => {
      this.currentRoute = event.urlAfterRedirects || event.url;
      this.mobileMenuOpen = false; // close sidebar on route change
    });
  }

  toggleMobileMenu() {
    this.mobileMenuOpen = !this.mobileMenuOpen;
  }

  toggleSimulationMode() {
    this.apiService.isSimulationMode = !this.apiService.isSimulationMode;
  }

  getRouteTitle(): string {
    if (this.currentRoute.includes('dashboard')) return 'Tableau de Bord';
    if (this.currentRoute.includes('grading')) return 'Vision & Inspection (Grading)';
    if (this.currentRoute.includes('pricing')) return 'Moteur de Pricing Prédictif';
    if (this.currentRoute.includes('product-sheet')) return 'Générateur de Fiche & Sync';
    if (this.currentRoute.includes('logistics')) return 'Routage & Logistique RSE';
    return 'Platana Engine';
  }
}
