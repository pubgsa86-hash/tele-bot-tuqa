export type ThemeParams = Record<string, string>;

type TgWebApp = {
  initData: string;
  colorScheme: string;
  themeParams: ThemeParams;
  ready(): void;
  expand(): void;
  close(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  MainButton?: {
    text: string;
    isVisible: boolean;
    setText(text: string): void;
    show(): void;
    hide(): void;
    setProgress(progress: boolean): void;
    enable(): void;
    disable(): void;
    onClick(fn: () => void): void;
    offClick(fn: () => void): void;
  };
  BackButton?: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(fn: () => void): void;
    offClick(fn: () => void): void;
  };
};

type AnyTg = TgWebApp | null;

function webapp(): AnyTg {
  const w = (window as unknown as { Telegram?: { WebApp?: TgWebApp } }).Telegram;
  return w && w.WebApp ? w.WebApp : null;
}

function safe(fn: () => void): void {
  try {
    fn();
  } catch {
    /* defensive: Telegram API may be absent or reject calls */
  }
}

export const telegram = {
  available: false,

  init(): void {
    const wa = webapp();
    if (!wa) return;
    telegram.available = true;
    applyTheme(wa);
    safe(() => wa.ready());
    safe(() => wa.expand());
    const bg = wa.themeParams.bg_color || (wa.colorScheme === "dark" ? "#1c1c1e" : "#ffffff");
    if (typeof wa.setBackgroundColor === "function") safe(() => wa.setBackgroundColor(bg));
    if (typeof wa.setHeaderColor === "function") safe(() => wa.setHeaderColor(bg));
  },

  get initData(): string {
    const wa = webapp();
    return wa ? wa.initData || "" : "";
  },

  close(): void {
    const wa = webapp();
    if (wa) safe(() => wa.close());
  },

  mainButton: {
    setText(text: string): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.setText(text));
    },
    show(): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.show());
    },
    hide(): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.hide());
    },
    setProgress(progress: boolean): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.setProgress(progress));
    },
    enable(): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.enable());
    },
    disable(): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.disable());
    },
    onClick(fn: () => void): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.onClick(fn));
    },
    offClick(fn: () => void): void {
      const wa = webapp();
      if (wa?.MainButton) safe(() => wa.MainButton!.offClick(fn));
    },
  },

  backButton: {
    show(): void {
      const wa = webapp();
      if (wa?.BackButton) safe(() => wa.BackButton!.show());
    },
    hide(): void {
      const wa = webapp();
      if (wa?.BackButton) safe(() => wa.BackButton!.hide());
    },
    onClick(fn: () => void): void {
      const wa = webapp();
      if (wa?.BackButton) safe(() => wa.BackButton!.onClick(fn));
    },
    offClick(fn: () => void): void {
      const wa = webapp();
      if (wa?.BackButton) safe(() => wa.BackButton!.offClick(fn));
    },
  },
};

function applyTheme(wa: TgWebApp): void {
  const params = wa.themeParams || {};
  const dark = wa.colorScheme === "dark";
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.setProperty("--color-scheme", dark ? "dark" : "light");
  const map: Record<string, string> = {
    "--tg-bg": params.bg_color,
    "--tg-text": params.text_color,
    "--tg-hint": params.hint_color,
    "--tg-link": params.link_color,
    "--tg-button": params.button_color,
    "--tg-button-text": params.button_text_color,
    "--tg-secondary-bg": params.secondary_bg_color,
  };
  for (const [name, value] of Object.entries(map)) {
    if (value) document.documentElement.style.setProperty(name, value);
  }
}