import { createFileRoute, redirect } from "@tanstack/react-router";

import { useAppName } from "../app-name";
import { useRootScreens } from "../root-screens";
import type { StarterScreenProps } from "../root-screens";

const STARTER_PATHS = {
  // i18n-exempt: a path
  file: "apps/web/src/routes/index.tsx",
  // i18n-exempt: a path
  directory: "apps/web/src/routes/",
};

const PlainStarter = ({ texts, appName, paths }: StarterScreenProps) => (
  <main className="mx-auto flex min-h-full max-w-2xl flex-col justify-center gap-2 p-8">
    <p className="text-sm">{texts.starterEyebrow}</p>
    <h1 className="text-3xl font-semibold">{appName}</h1>
    <p>
      {texts.starterHint({
        // Paths read left to right in any language.
        file: <code dir="ltr">{paths.file}</code>,
        directory: <code dir="ltr">{paths.directory}</code>,
      })}
    </p>
  </main>
);

/** The starter page: the contributed screen when there is one (`root-screens.tsx`), else a plain one. */
const Home = () => {
  const appName = useAppName();
  const { screens, texts } = useRootScreens();
  const Screen = screens.Starter ?? PlainStarter;

  return <Screen texts={texts} appName={appName} paths={STARTER_PATHS} />;
};

export const Route = createFileRoute("/")({
  beforeLoad: ({ context }) => {
    const to = context.landingPath();

    if (to !== undefined && to !== "" && to !== "/") {
      // oxlint-disable-next-line typescript/only-throw-error -- TanStack Router's redirect is thrown, by design
      throw redirect({ href: to });
    }
  },
  component: Home,
});
