"""Persisted design decisions owned by the harness before code generation."""
from pydantic import BaseModel, Field


class DesignBrief(BaseModel):
    version: int = 2
    project_type: str = 'business_portfolio'
    original_request: str
    design_direction: str
    tone: list[str]
    visual_principles: list[str]
    color_strategy: dict
    typography_strategy: dict
    spacing_strategy: dict
    layout_strategy: dict
    image_strategy: dict
    motion_strategy: dict
    responsive_strategy: dict
    section_specs: list[dict] = Field(min_length=1)
    asset_strategy: list[dict] = Field(min_length=1)
    quality_rules: list[str]
    allow_playful_icons: bool = False


class DesignAgent:
    def create(self, request, plan):
        playful = any(word in request.lower() for word in ('playful', 'emoji', 'cartoon'))
        light = any(word in request.lower() for word in ('light theme', 'light background', 'bright', 'white background'))
        specs = [
            {'section': 'navigation', 'component': 'Navbar', 'purpose': 'orient visitors', 'layout': 'wordmark, Services / Work / About / Contact links, contact action', 'interaction': 'hover, active link, accessible mobile menu'},
            {'section': 'hero', 'component': 'Hero', 'purpose': 'establish positioning immediately', 'layout': 'asymmetric two-column editorial composition', 'headline': 'distinctive business-specific display headline', 'actions': ['View selected work', 'Start a project'], 'visual_required': True, 'visual_type': 'editorial imagery or layered SVG composition', 'motion': ['headline reveal', 'visual reveal', 'button hover']},
            {'section': 'portfolio', 'component': 'Portfolio', 'purpose': 'demonstrate work through visuals and outcomes', 'layout': 'one large featured project and two supporting cards', 'project_fields': ['visual', 'category', 'title', 'outcome', 'view project affordance'], 'visual_required': True, 'interaction': 'image scale and card hover'},
            {'section': 'services', 'component': 'Services', 'purpose': 'explain capabilities', 'layout': 'aligned numbered rows or refined line-icon cards with capability tags', 'interaction': 'staggered reveal and hover'},
            {'section': 'about', 'component': 'About', 'purpose': 'build credibility', 'layout': 'editorial copy paired with portrait or abstract visual'},
            {'section': 'process', 'component': 'Process', 'purpose': 'show how engagements work', 'layout': 'numbered progression with differentiated step hierarchy'},
            {'section': 'testimonials', 'component': 'Testimonials', 'purpose': 'provide credible social proof', 'layout': 'oversized editorial quote, name, role and company'},
            {'section': 'contact', 'component': 'ContactCTA', 'purpose': 'convert interest into contact', 'layout': 'distinct accent surface with strong headline, support copy and primary/secondary actions', 'interaction': 'clear focus, contrasting buttons, hover transitions'},
            {'section': 'footer', 'component': 'Footer', 'purpose': 'finish the experience', 'layout': 'wordmark, navigation, contact, social links, copyright and brand statement'},
        ]
        for spec in specs:
            spec['path'] = plan.get('expected_components', {}).get(spec['component'])
            spec['dom_marker'] = 'data-section="' + spec['section'] + '"'
        assets = [{'section': 'hero', 'aspect_ratio': '16:10', 'dimensions': [1600, 1000], 'mood': 'editorial architectural brand composition', 'type': 'local image or layered SVG', 'fallback': 'multi-layer SVG artwork with geometry, texture and typographic detail', 'path': plan.get('expected_assets', {}).get('hero')},
                  {'section': 'portfolio', 'aspect_ratio': '4:3', 'dimensions': [1200, 900], 'mood': 'distinct project-specific case study previews', 'type': 'local image, mock interface or original graphic', 'fallback': 'three distinct SVG project thumbnails', 'paths': plan.get('expected_assets', {}).get('portfolio', [])},
                  {'section': 'about', 'aspect_ratio': '3:4', 'dimensions': [900, 1200], 'mood': 'editorial studio story', 'type': 'recommended image or graphic', 'fallback': 'deliberate typographic composition'},
                  {'section': 'testimonials', 'aspect_ratio': '1:1', 'dimensions': [128, 128], 'type': 'optional avatar', 'fallback': 'client initials with editorial quote treatment'}]
        return DesignBrief(original_request=request,
            design_direction='playful contemporary studio' if playful else 'premium editorial digital studio',
            tone=['confident', 'creative', 'contemporary', 'high-end'],
            visual_principles=['strong typography hierarchy', 'image-led composition', 'intentional whitespace', 'asymmetric grid', 'refined interaction', 'editorial project storytelling'],
            color_strategy={'base': 'warm neutral' if light else 'charcoal / deep forest', 'secondary': 'tonal variations', 'light_surface': 'warm neutral', 'accent': 'restrained contrasting accent', 'tokens': ['--color-bg-primary', '--color-bg-secondary', '--color-bg-elevated', '--color-text-primary', '--color-text-muted', '--color-accent', '--color-border', '--color-light-section'], 'rule': 'Use contrasting section surfaces; avoid one tone across the whole page.'},
            typography_strategy={'display': 'expressive grotesk or editorial serif', 'body': 'modern neutral sans-serif', 'display_scale': 'clamp(4rem, 8vw, 8rem)', 'h1': 'clamp(3rem, 6vw, 6rem)', 'h2': 'clamp(2rem, 4vw, 4rem)', 'body_large': '1.25rem', 'body': '1rem', 'small': '.8rem', 'rule': 'Set line-height, letter-spacing, weight and readable max-width intentionally.'},
            spacing_strategy={'scale_px': [8, 16, 24, 40, 64, 96, 128], 'tokens': ['--space-xs', '--space-sm', '--space-md', '--space-lg', '--space-xl', '--space-section']},
            layout_strategy={'page_max_width': 1440, 'content_max_width': 1240, 'desktop_columns': 12, 'tablet_columns': 8, 'mobile_columns': 4, 'rule': 'Vary section composition; do not center everything or repeat equal three-column grids.'},
            image_strategy={'hero_visual': 'required', 'portfolio_images': 'required', 'about_visual': 'recommended', 'image_style': 'editorial architecture, brand work and product mockups', 'local_fallback_required': True, 'workspace_asset_mode': 'local_svg_css_fallback', 'rule': 'Use loaded local assets or deliberate layered art; never empty rectangles, image-here text or bare gradients.'},
            motion_strategy={'scroll_reveal': True, 'image_hover': True, 'button_microinteraction': True, 'section_transition': True, 'reduced_motion': True, 'implementation': 'Use installed motion library or CSS / IntersectionObserver; content must remain visible without animation.'},
            responsive_strategy={'desktop': 'large editorial composition', 'tablet': 'simplified grid', 'mobile': 'single-column hierarchy and accessible navigation', 'viewports': [1440, 390]},
            section_specs=specs, asset_strategy=assets, allow_playful_icons=playful,
            quality_rules=['No empty hero visual', 'No text-only portfolio', 'No generic emoji treatment unless explicitly playful', 'Strong CTA hierarchy', 'Developed editorial testimonials and footer', 'Meaningful assets and varied section composition', 'Visible keyboard focus and reduced-motion support', 'Professional studio quality in desktop and mobile screenshots']).model_dump()
