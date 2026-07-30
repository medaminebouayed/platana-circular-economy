import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { GradingComponent } from './grading/grading.component';
import { PricingComponent } from './pricing/pricing.component';
import { ProductSheetComponent } from './product-sheet/product-sheet.component';
import { LogisticsComponent } from './logistics/logistics.component';

const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'dashboard', component: DashboardComponent },
  { path: 'grading', component: GradingComponent },
  { path: 'pricing', component: PricingComponent },
  { path: 'product-sheet', component: ProductSheetComponent },
  { path: 'logistics', component: LogisticsComponent },
  { path: '', redirectTo: '/login', pathMatch: 'full' },
  { path: '**', redirectTo: '/login' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
