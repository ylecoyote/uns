/**
 * PlaceholderPage component for routes not yet implemented.
 *
 * Displays a consistent placeholder message for pages that are
 * planned but not yet built.
 */

export interface PlaceholderPageProps {
  /** Page title */
  title: string;
  /** Page description */
  description: string;
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <div className="placeholder-page">
      <h1>{title}</h1>
      <p>{description}</p>
      <p className="placeholder-note">Page not yet implemented.</p>
    </div>
  );
}

export default PlaceholderPage;
