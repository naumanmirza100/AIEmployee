import React, { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet';

/**
 * Shared shell for the public legal documents (privacy policy, terms).
 *
 * Both documents are reference material, not prose to be read front to back —
 * a company admin lands here to check one clause, and Google's OAuth reviewer
 * lands here to find the Limited Use disclosure. So the clause numbers double
 * as the navigation: the index on the left is built from `sections` and tracks
 * whichever clause is currently on screen.
 *
 * `sections` is an array of { id, title, body } where body is JSX.
 */
const LegalPage = ({ title, description, updated, intro, sections }) => {
  const [activeId, setActiveId] = useState(sections[0]?.id);

  useEffect(() => {
    // rootMargin pulls the trigger line to the upper third of the viewport so a
    // clause counts as "active" once its heading settles near the top, rather
    // than only when the whole section is in view.
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 }
    );

    sections.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [sections]);

  return (
    <div className="bg-background">
      <Helmet>
        <title>{title} | Pay Per Project</title>
        <meta name="description" content={description} />
      </Helmet>

      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <header className="border-b pt-20 pb-10">
          <h1 className="font-heading text-4xl sm:text-5xl text-foreground">{title}</h1>
          <p className="mt-3 text-sm text-muted-foreground">Last updated {updated}</p>
          <p className="mt-6 max-w-[68ch] text-muted-foreground leading-relaxed">{intro}</p>
        </header>

        <div className="grid gap-12 py-12 lg:grid-cols-[13rem_1fr] lg:gap-16">
          <nav aria-label="Sections" className="lg:sticky lg:top-24 lg:self-start">
            <ol className="space-y-1">
              {sections.map(({ id, title: sectionTitle }, i) => {
                const isActive = id === activeId;
                return (
                  <li key={id}>
                    <a
                      href={`#${id}`}
                      aria-current={isActive ? 'true' : undefined}
                      className={`flex gap-3 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        isActive
                          ? 'bg-secondary/60 text-foreground'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <span className={isActive ? 'text-primary' : 'text-muted-foreground/60'}>
                        {i + 1}
                      </span>
                      <span>{sectionTitle}</span>
                    </a>
                  </li>
                );
              })}
            </ol>
          </nav>

          <div className="min-w-0">
            {sections.map(({ id, title: sectionTitle, body }, i) => (
              <section
                key={id}
                id={id}
                className="scroll-mt-24 border-b py-10 first:pt-0 last:border-b-0"
              >
                <h2 className="font-heading text-2xl text-foreground">
                  <span className="mr-3 text-muted-foreground/50">{i + 1}</span>
                  {sectionTitle}
                </h2>
                <div className="mt-5 max-w-[68ch] space-y-4 leading-relaxed text-muted-foreground [&_a]:text-primary [&_a:hover]:underline [&_strong]:text-foreground [&_strong]:font-medium">
                  {body}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

/** Bulleted list used inside a clause body. */
export const LegalList = ({ items }) => (
  <ul className="space-y-2">
    {items.map((item, i) => (
      <li key={i} className="flex gap-3">
        <span aria-hidden="true" className="mt-2.5 h-px w-3 shrink-0 bg-muted-foreground/40" />
        <span>{item}</span>
      </li>
    ))}
  </ul>
);

/**
 * The one emphatic element on either page: the exact Google scope we request
 * and the boundary on it. Everything else stays quiet so this reads first.
 */
export const ScopeCallout = ({ children }) => (
  <div className="border-l-2 border-primary bg-secondary/40 py-5 pl-5 pr-5 sm:pr-6">
    {children}
  </div>
);

export default LegalPage;
