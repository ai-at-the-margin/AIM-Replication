import { useEffect, useState } from "react";

export function useRoute(): string {
  const read = () => (window.location.hash.replace(/^#\/?/, "").split("?")[0] || "overview");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => {
      setRoute(read());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function go(route: string) {
  window.location.hash = `#/${route}`;
}
