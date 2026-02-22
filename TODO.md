# Hacxgent Development Roadmap

This document outlines the planned features, improvements, and future directions for the Hacxgent project.

## 🚀 High Priority (Next Release)

- [ ] **Multimodal Support**: Add image upload and analysis support (GPT-4o / Claude 3.5 Vision) to allow the agent to "see" UI bugs, diagrams, and screenshots.
- [ ] **Dynamic Tool Creation**: Implement a `hacxgent tool create <name>` command that generates a boilerplate for user-defined tools, making it easy for developers to extend the agent.
- [ ] **Enhanced Memory Management**: 
    - [ ] Implement **Hierarchical Summarization** for very long sessions.
    - [ ] Add **Vector-based Long-term Memory** (RAG) for project-wide semantic search.
    - [ ] Support for **Pinned Context**: Allow users to "pin" specific messages so they are never redacted.


## 🎨 User Experience & UI

- [ ] **Rich Animations**: 
    - [ ] Add more banner styles (e.g., "Fire", "Wave", "Scanline").
    - [ ] Implement smooth transitions between UI states.
- [ ] **Deep Customization**: 
    - [ ] Full Theme Engine: Support for custom `.tcss` files for total UI control.
    - [ ] Granular Keybinding Support: Rebind any shortcut (Vim-style or Emacs-style).
- [ ] **Interactive Onboarding**: A step-by-step tutorial inside the terminal to teach new users the "Surgical Context" workflow.

## 📚 Documentation & Community

- [ ] **Dedicated Documentation Site**: Build a beautiful Docusaurus/MkDocs site for Hacxgent.
- [ ] **Tool Gallery**: A community-driven repository of custom tools and "Skills."
- [ ] **API Reference**: Auto-generated documentation for the Hacxgent core library for programmatic use.

---
*Want to contribute? Check out [CONTRIBUTING.md](.github/CONTRIBUTING.md) to get started!*
