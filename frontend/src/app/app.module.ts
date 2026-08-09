import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { HttpClientModule, HTTP_INTERCEPTORS } from '@angular/common/http';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
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
import { AuthInterceptor } from './interceptors/auth.interceptor';

@NgModule({
  declarations: [
    AppComponent,
    DashboardComponent,
    GradingComponent,
    PricingComponent,
    ProductSheetComponent,
    LogisticsComponent,
    UserPortalComponent,
    UserLoginComponent,
    AdminLoginComponent,
    UserSettingsComponent,
    AdminSettingsComponent,
    UserRegisterComponent
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    FormsModule,
    HttpClientModule
  ],
  providers: [
    {
      provide: HTTP_INTERCEPTORS,
      useClass: AuthInterceptor,
      multi: true
    }
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
