import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { TRANSLATIONS, Translations } from './translations';

@Injectable({ providedIn: 'root' })
export class TranslationService {
  private currentLangSubject = new BehaviorSubject<string>('fr');
  public currentLang$ = this.currentLangSubject.asObservable();
  private dict: Translations = TRANSLATIONS.fr;

  constructor() {
    const saved = localStorage.getItem('platana-lang');
    this.setLang(saved === 'en' ? 'en' : 'fr');
  }

  setLang(lang: string): void {
    const normalized = lang === 'en' ? 'en' : 'fr';
    localStorage.setItem('platana-lang', normalized);
    this.dict = TRANSLATIONS[normalized];
    this.currentLangSubject.next(normalized);
  }

  getLang(): string {
    return this.currentLangSubject.value;
  }

  /** Translate a key. Falls back to the key itself so missing keys are visible in the UI. */
  t(key: string): string {
    return this.dict && this.dict[key] !== undefined ? this.dict[key] : key;
  }

  /** Translate a key and substitute {{name}} placeholders. */
  tWith(key: string, params: Record<string, string | number>): string {
    let out = this.t(key);
    for (const name of Object.keys(params)) {
      out = out.replace(new RegExp('{{' + name + '}}', 'g'), String(params[name]));
    }
    return out;
  }
}