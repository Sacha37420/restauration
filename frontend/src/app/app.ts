import { Component, inject } from '@angular/core';
import { RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { SidebarComponent } from './shared/sidebar/sidebar.component';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map, startWith } from 'rxjs';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, SidebarComponent],
  template: `
    @if (isPublic()) {
      <router-outlet />
    } @else {
      <div class="app-shell">
        <app-sidebar />
        <div class="main-content">
          <router-outlet />
        </div>
      </div>
    }
  `,
})
export class AppComponent {
  private router = inject(Router);

  isPublic = toSignal(
    this.router.events.pipe(
      filter(e => e instanceof NavigationEnd),
      map((e: NavigationEnd) => e.urlAfterRedirects.startsWith('/commander')),
      startWith(window.location.pathname.startsWith('/commander')),
    ),
    { initialValue: window.location.pathname.startsWith('/commander') },
  );
}

export { AppComponent as App };
