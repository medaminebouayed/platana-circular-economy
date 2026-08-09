import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DashboardComponent } from './dashboard/dashboard.component';
import { GradingComponent } from './grading/grading.component';
import { PricingComponent } from './pricing/pricing.component';
import { ProductSheetComponent } from './product-sheet/product-sheet.component';
import { LogisticsComponent } from './logistics/logistics.component';
import { UserPortalComponent } from './user-portal/user-portal.component';
import { UserLoginComponent } from './user-login/user-login.component';
import { AdminLoginComponent } from './admin-login/admin-login.component';
import { UserSettingsComponent } from './user-settings/user-settings.component';
import { AdminSettingsComponent } from './admin-settings/admin-settings.component';
import { UserRegisterComponent } from './user-register/user-register.component';
import { AuthGuard } from './guards/auth.guard';

const routes: Routes = [
  // ── Public routes (no auth required) ──────────────────────────
  { path: 'login/user',  component: UserLoginComponent },
  { path: 'login/admin', component: AdminLoginComponent },
  { path: 'register',    component: UserRegisterComponent },

  // ── User routes (USER or ADMIN can access) ─────────────────────
  {
    path: 'user-portal',
    component: UserPortalComponent,
    canActivate: [AuthGuard],
    data: { roles: ['USER', 'ADMIN'] }
  },
  {
    path: 'settings/user',
    component: UserSettingsComponent,
    canActivate: [AuthGuard],
    data: { roles: ['USER', 'ADMIN'] }
  },

  // ── Admin-only routes ──────────────────────────────────────────
  {
    path: 'dashboard',
    component: DashboardComponent,
    canActivate: [AuthGuard],
    data: { roles: ['ADMIN'] }
  },
  {
    path: 'grading',
    component: GradingComponent,
    canActivate: [AuthGuard],
    data: { roles: ['ADMIN'] }
  },
  {
    path: 'pricing',
    component: PricingComponent,
    canActivate: [AuthGuard],
    data: { roles: ['ADMIN'] }
  },
  {
    path: 'product-sheet',
    component: ProductSheetComponent,
    canActivate: [AuthGuard],
    data: { roles: ['ADMIN'] }
  },
  {
    path: 'logistics',
    component: LogisticsComponent,
    canActivate: [AuthGuard],
    data: { roles: ['ADMIN'] }
  },
  {
    path: 'settings/admin',
    component: AdminSettingsComponent,
    canActivate: [AuthGuard],
    data: { roles: ['ADMIN'] }
  },

  // ── Fallback ──────────────────────────────────────────────────
  { path: '', redirectTo: '/login/user', pathMatch: 'full' },
  { path: '**', redirectTo: '/login/user' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
