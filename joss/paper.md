---
title: 'hdsemg-pipe: A modular application to guide users through high-density surface EMG processing, from a raw signal to motor unit decomposition'
tags:
  - Python
  - electromyography
  - HD-sEMG
  - motor units
  - signal processing
  - PyQt5
  - CoVISI
  - neuromuscular physiology
authors:
  - name: Johannes Kasser
    orcid: 0009-0009-3124-7755
    corresponding: true
    affiliation: "1"
  - name: Harald Penasso
    orcid: 0000-0002-4583-9948
    affiliation: "2"
affiliations:
  - name: [Medical University Vienna], [Austria]
    index: 1
  - name: [University of Applied Sciences Vienna], [Austria]
    index: 2
date: 30 January 2026
bibliography: paper.bib
---

# Summary

High-density surface electromyography (HD-sEMG) records electrical signals from muscles using electrode arrays, revealing individual motor unit activity. However, raw HD-sEMG signals require extensive preprocessing and quality control before motor unit decomposition can produce meaningful results. `hdsemg-pipe` provides an integrated application guiding users through a complete 12-step workflow from raw signal acquisition to final motor unit analysis. The software addresses the critical preprocessing phase with features including line noise removal, RMS-based quality assessment, region-of-interest definition, and an interactive channel selection framework for identifying and removing problematic channels. By integrating established tools like `MUedit` [@avrillon2024muedit] for manual motor unit cleaning within a comprehensive preprocessing and quality control workflow, `hdsemg-pipe` eliminates the fragmentation that characterizes current HD-sEMG analysis. The application serves researchers in motor control, biomechanics, clinical assessment, and rehabilitation who need accessible, open-source tools with guided workflows.

# Statement of Need

Successful motor unit decomposition from HD-sEMG requires careful preprocessing and quality control before applying decomposition algorithms. Raw HD-sEMG signals contain electrical line noise, electrode artifacts, baseline drift, and channels with poor signal quality that can compromise or completely prevent accurate motor unit identification. The preprocessing workflow involves multiple specialized steps: removing line noise interference, assessing signal quality through RMS analysis, selecting appropriate signal regions, identifying and excluding problematic channels, and configuring multi-grid electrode arrays. Each step requires domain knowledge and careful execution to ensure downstream decomposition accuracy.

Currently, researchers must manually orchestrate these preprocessing steps across disconnected tools and custom scripts, leading to inconsistent methodologies, increased error risk, and substantial time investment. While excellent tools exist for specific tasks—`openhdemg` [@valli2023openhdemg] for motor unit analysis and `MUedit` [@avrillon2024muedit] for manual cleaning—no integrated solution guides users through the complete preprocessing-to-analysis pipeline with enforced sequential workflows and built-in quality control.

`hdsemg-pipe` addresses this gap by providing a wizard-based application that integrates preprocessing, quality assessment, channel selection, decomposition configuration, and post-processing into a unified workflow. The channel selection framework enables interactive identification of problematic channels through visual inspection and quality metrics. The application integrates `MUedit` as a key component for motor unit cleaning rather than replacing it, positioning manual cleaning within the broader context of complete signal processing. Target users include researchers in motor control, biomechanics, clinical assessment, and rehabilitation who need accessible preprocessing tools but may lack programming expertise or resources for commercial software.

# State of the Field

`openhdemg` [@valli2023openhdemg] is an excellent open-source Python library providing motor unit analysis functions and decomposition algorithms, but requires programming skills and offers no GUI or guided workflow for preprocessing steps. `MUedit` [@avrillon2024muedit] provides sophisticated MATLAB-based interfaces for manual motor unit cleaning and represents the gold standard for this specific task, but focuses exclusively on the post-decomposition cleaning phase without addressing upstream preprocessing requirements. Commercial solutions like DEMUSE offer GUI-based workflows but require expensive licenses that may be prohibitive for many research groups.

Critically, no existing open-source tool addresses the complete preprocessing pipeline with guided workflows. Researchers must manually combine multiple tools and custom scripts to progress from raw signals through noise removal, quality assessment, channel selection, decomposition configuration, and final analysis. This fragmentation leads to methodological inconsistencies and prevents researchers without programming expertise from performing rigorous HD-sEMG analysis.

Building `hdsemg-pipe` rather than extending existing tools reflects fundamental architectural differences. `openhdemg` was designed as a library for programmatic use, not an end-user application with enforced sequential workflows. `MUedit` intentionally focuses on the manual cleaning task where it excels. `hdsemg-pipe` complements these tools by providing the surrounding preprocessing infrastructure and workflow orchestration.

Key contributions include: (1) Complete preprocessing workflow from raw signals through quality control to decomposition-ready data; (2) Interactive channel selection framework with quality metrics and visual inspection; (3) Integration of `MUedit` within the broader workflow via bidirectional format translation; (4) Multi-grid electrode array support with per-grid metadata preservation; (5) Automatic state reconstruction enabling interrupted multi-day analyses; (6) Open-source alternative to commercial solutions with accessible GUI interface.

# Software Design

`hdsemg-pipe` implements a 12-step enforced sequential workflow embedding methodological best practices: file import → grid association → line noise removal → RMS quality assessment → ROI definition → channel selection → decomposition results → multi-grid configuration → optional CoVISI pre-filtering → `MUedit` cleaning → optional CoVISI post-validation → final results. This architecture prevents common errors like applying decomposition to noise-contaminated signals or attempting analysis before channel quality assessment. Each step validates prerequisites before activation, ensuring methodologically sound processing order.

The preprocessing phase (steps 1-6) represents the core contribution. Line noise removal offers multiple methods including MNE-Python filters and MATLAB CleanLine integration. RMS quality assessment provides per-channel noise analysis with quality categorization (Excellent ≤5µV → Bad >20µV), enabling researchers to identify problematic recordings before investing decomposition time. The channel selection framework integrates with the external `hdsemg-select` tool, providing interactive interfaces for marking channels as good or bad based on visual inspection and quality metrics. This preprocessing infrastructure ensures decomposition algorithms receive clean, quality-controlled input signals.

`MUedit` integration (step 10) demonstrates the complementary relationship between tools. Bidirectional format translation between `openhdemg` JSON and `MUedit` MATLAB v7.3 (HDF5) enables seamless handoff to `MUedit` for its specialized manual cleaning capabilities, then automatic re-import of cleaned results. The system handles technical challenges including zero-based/one-based indexing conversion and proper h5py reference type handling. This integration positions `MUedit` within the complete workflow rather than as a disconnected tool requiring manual file management.

Global state management tracks progress across steps in structured directories with ten standardized subfolders. Automatic state reconstruction analyzes folder structure when opening projects, restoring completion states and enabling interrupted analyses. Multi-grid support preserves per-grid metadata with unified coordinate systems, enabling complex experimental designs while maintaining anatomically meaningful data structure.

# Research Impact Statement

`hdsemg-pipe` addresses a critical gap in HD-sEMG research infrastructure by providing the missing preprocessing and workflow orchestration layer. The software demonstrates community readiness through comprehensive MkDocs documentation, PyPI publication, active GitHub repository, and six months of open development with iterative refinement based on early user feedback.

The integrated preprocessing workflow has practical significance for research productivity. By consolidating signal cleaning, quality assessment, channel selection, and tool integration into a single application with state management, researchers avoid the time-consuming manual file transfers and workflow tracking currently required. The wizard interface enforces methodologically sound processing sequences, reducing the risk of errors that could compromise research validity—particularly important as HD-sEMG adoption expands beyond specialized signal processing laboratories.

Target applications span motor unit recruitment analysis, muscle fatigue studies, clinical neuromuscular assessment, rehabilitation research, and athletic performance analysis. The channel selection framework and quality assessment tools help researchers identify data quality issues early, preventing wasted computational resources on decomposing problematic signals.

The open-source nature addresses research equity by providing a free alternative to commercial workflows. The accessible GUI enables researchers without programming backgrounds—including clinicians, physical therapists, and sports scientists—to perform rigorous HD-sEMG preprocessing and analysis. Technical validation comes from integration with established tools (`openhdemg` [@valli2023openhdemg], `MUedit` [@avrillon2024muedit]) and implementation of published standards for quality metrics [@taleshi2025bloodflow; @delvecchio2019tutorial].

Near-term impact is credible given growing HD-sEMG adoption, increasing hardware availability, established need for preprocessing workflows, and absence of open-source solutions providing integrated preprocessing-to-analysis pipelines with guided interfaces.

# AI Usage Disclosure

Generative AI tools (Claude 3.5 Sonnet, GitHub Copilot) were used to assist with code generation, documentation writing, and debugging during software development. All core design decisions, including the two-stage CoVISI quality framework, wizard-based architecture, state management system, and format translation approach, were conceived and validated by the human authors. AI tools did not make architectural, scientific methodology, or research significance decisions. All code has been reviewed, tested, and validated by the authors to ensure correctness and adherence to software engineering best practices. The scientific foundation of the quality standards is based on peer-reviewed literature [@taleshi2025bloodflow], not AI-generated content.

# Acknowledgements

We acknowledge the developers of `openhdemg` (Giacomo Valli and colleagues) and `MUedit` (Simon Avrillon and colleagues) for creating the foundational tools that `hdsemg-pipe` builds upon and integrates. We thank early users and testers who provided valuable feedback during software development, particularly regarding the CoVISI filtering workflow and user interface design. This work received no specific funding from agencies in the public, commercial, or not-for-profit sectors.

# References
