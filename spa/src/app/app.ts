import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { TopChrome } from './shared/chrome/top-chrome';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, TopChrome],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
