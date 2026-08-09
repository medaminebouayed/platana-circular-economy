import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { AuthService, User } from './services/auth.service';
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
  isDarkTheme = false;

  constructor(
    public authService: AuthService,
    private router: Router
  ) {
    this.initTheme();
  }

  initTheme() {
    const savedTheme = localStorage.getItem('platana-theme');
    if (savedTheme) {
      this.isDarkTheme = savedTheme === 'dark';
    } else {
      // Check system preference
      this.isDarkTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    this.applyTheme();
  }

  toggleTheme() {
    this.isDarkTheme = !this.isDarkTheme;
    localStorage.setItem('platana-theme', this.isDarkTheme ? 'dark' : 'light');
    this.applyTheme();
  }

  applyTheme() {
    if (this.isDarkTheme) {
      document.body.classList.add('dark-theme');
    } else {
      document.body.classList.remove('dark-theme');
    }
  }

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



  getRouteTitle(): string {
    if (this.currentRoute.includes('dashboard')) return 'Espace Admin — Validation';
    if (this.currentRoute.includes('user-portal')) return 'Déposer un Produit';
    if (this.currentRoute.includes('grading')) return 'Vision & Inspection (Grading)';
    if (this.currentRoute.includes('pricing')) return 'Moteur de Pricing Prédictif';
    if (this.currentRoute.includes('product-sheet')) return 'Générateur de Fiche & Sync';
    if (this.currentRoute.includes('logistics')) return 'Routage & Logistique RSE';
    if (this.currentRoute.includes('settings/admin')) return 'Paramètres Admin';
    if (this.currentRoute.includes('settings/user')) return 'Paramètres';
    return 'Platana Engine';
  }
}
