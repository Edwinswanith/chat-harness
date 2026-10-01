async ({ allowPlayful = false, expectedSections = [] } = {}) => {
  const visible = e => e && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0 && getComputedStyle(e).visibility !== 'hidden' && Number(getComputedStyle(e).opacity) > 0;
  const all = (s, root = document) => [...root.querySelectorAll(s)].filter(visible);
  const section = name => document.querySelector(`[data-section="${name}"],#${name}`);
  const heading = all('h1')[0];
  const hero = section('hero') || heading?.closest('section,header');
  const work = section('portfolio') || document.querySelector('#work,#projects');
  const services = section('services');
  const quote = section('testimonials');
  const contact = section('contact') || document.querySelector('#cta');
  const footer = all('footer')[0];
  const nav = all('nav,header')[0];
  const sections = all('main section,main > article');
  const imageReady = e => e.complete && e.naturalWidth >= 80 && e.naturalHeight >= 40 && !/placeholder|image.here/i.test(e.getAttribute('src') || '');
  const graphic = e => all('svg', e).some(svg => svg.querySelectorAll('path,rect,circle,polygon,line,text,ellipse').length >= 4);
  const composition = e => all('[data-art-layer],.art-layer', e).length >= 3;
  const meaningful = e => !!e && (all('img', e).some(imageReady) || graphic(e) || composition(e));
  const visuals = hero ? all('[data-visual],.hero-visual,.hero-image,.hero-art', hero) : [];
  const emptyHero = !meaningful(hero) || visuals.some(e => !meaningful(e) && !e.matches('img,svg'));
  const placeholders = all('main [data-visual],main img,main figure').some(e => /image here|placeholder image|coming soon visual/i.test(e.textContent || e.getAttribute('alt') || ''));
  const cards = work ? all('[data-project],article,.project-card', work) : [];
  const visualProjects = cards.length >= 3 && cards.every(card => meaningful(card) && all('h2,h3,h4', card).length > 0 && all('a,button', card).length > 0 && (card.textContent || '').trim().length >= 50);
  const emoji = /[\u{1F300}-\u{1FAFF}]/u;
  const surfaces = new Set(sections.map(e => getComputedStyle(e).backgroundColor).filter(c => !/rgba\(0, 0, 0, 0\)|transparent/.test(c)));
  const h1size = heading ? parseFloat(getComputedStyle(heading).fontSize) : 0;
  const bodySize = parseFloat(getComputedStyle(document.body).fontSize);
  const ctas = contact ? all('a,button', contact) : [];
  const links = nav ? all('a,button', nav) : [];
  const navLinks = links.filter(e => e.matches('a'));
  const navigationComplete = navLinks.length >= 4 && ['service', 'work|portfolio|project', 'about', 'contact'].every(pattern => navLinks.some(e => new RegExp(pattern, 'i').test((e.textContent || '') + (e.getAttribute('href') || ''))));
  const touched = [...links, ...ctas, ...(cards.flatMap(card => all('a,button,img', card)))];
  const stateRule = [...document.styleSheets].some(sheet => {
    try { return [...sheet.cssRules].some(rule => /:hover|:focus-visible|:focus/.test(rule.cssText)); } catch { return false; }
  });
  const reduceRule = [...document.styleSheets].some(sheet => {
    try { return [...sheet.cssRules].some(rule => /prefers-reduced-motion/.test(rule.cssText)); } catch { return false; }
  });
  const reveal = all('[data-reveal],.reveal,[data-motion]').length > 0 || all('main *').some(e => getComputedStyle(e).animationName !== 'none');
  const assets = await Promise.all(all('img').map(async e => {
    try { await e.decode(); return imageReady(e); } catch { return false; }
  }));
  const marker = {Navbar: 'navigation', Hero: 'hero', Services: 'services', Portfolio: 'portfolio', About: 'about', Process: 'process', Testimonials: 'testimonials', ContactCTA: 'contact', Footer: 'footer'};
  const rendered = expectedSections.every(name => name === 'Navbar' ? !!nav : name === 'Footer' ? !!footer : visible(section(marker[name] || name.toLowerCase())));
  const contrasts = ctas.map(e => {
    const rgb = c => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const lum = c => rgb(c).map(n => n / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4).reduce((s, n, i) => s + n * [.2126, .7152, .0722][i], 0);
    let bg = e; while (bg.parentElement && /rgba\(0, 0, 0, 0\)|transparent/.test(getComputedStyle(bg).backgroundColor)) bg = bg.parentElement;
    const a = lum(getComputedStyle(e).color), b = lum(getComputedStyle(bg).backgroundColor);
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05) >= 3;
  });
  return {
    checks: {no_overflow: document.documentElement.scrollWidth <= innerWidth + 2, navigation: !!nav && navigationComplete,
      hero: !!heading && h1size >= (innerWidth < 500 ? 36 : 48), cta: ctas.length >= 2,
      sections: sections.length >= 7, planned_sections_rendered: rendered, footer: !!footer,
      styled_navigation: nav ? all('ul,ol', nav).every(e => getComputedStyle(e).listStyleType === 'none') : false,
      typography: !!heading && !/Times New Roman/.test(getComputedStyle(heading).fontFamily) && h1size / bodySize >= 2.25,
      spacing: sections.every(e => e.getBoundingClientRect().height < innerHeight * 6),
      meaningful_hero_visual: !emptyHero, portfolio_visuals: visualProjects, no_placeholders: !placeholders,
      assets_loaded: assets.every(Boolean), refined_service_icons: allowPlayful || !emoji.test(services?.textContent || ''),
      tonal_hierarchy: surfaces.size >= 2, polished_interactions: stateRule && touched.length > 0,
      motion_strategy: reveal && reduceRule, cta_contrast: ctas.length > 0 && contrasts.every(Boolean),
      editorial_testimonials: !!quote && all('blockquote,q', quote).length > 0 && all('cite', quote).length > 0,
      developed_footer: !!footer && all('a', footer).length >= 4 && (footer.textContent || '').trim().length >= 60,
      mobile_targets: innerWidth >= 500 || touched.every(e => !e.matches('a,button') || e.getBoundingClientRect().height >= 32)},
    evidence: {surface_count: surfaces.size, project_count: cards.length, heading_size: h1size,
      visual_container_count: visuals.length, empty_hero: emptyHero, reveal_present: reveal, reduced_motion: reduceRule}
  };
}
