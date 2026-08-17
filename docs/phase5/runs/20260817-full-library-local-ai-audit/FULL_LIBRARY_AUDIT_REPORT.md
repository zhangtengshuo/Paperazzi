# FULL_LIBRARY_AUDIT_REPORT

> Status: **FAIL — correspondence population remains blocked**. The full-library audit completed, but the conservative gate `FP = 0` and `recall >= 0.90` did not pass. No production fix was applied during this audit.

## Run identity

- Git branch: `fix/correspondence-evidence-v3-clean`
- Git revision tested: `95550de88cdf4a79dae8a7960a40155b62a57db1`
- Runtime: `Python 3.13.15` via micromamba environment `Paperazzi`
- Audit mode: read-only PDF/database QA; no Zotero or Paperazzi semantic writes
- Requested legacy DB path `data/phase4-validation/paperazzi.sqlite3` was not usable by the current scanner because it is at migration `0005_identity_history_constraints` and lacks `document_roles`.
- Audit DB actually used: `/home/shuo/develop/Paperazzi/data/phase5-validation/phase5_5/paperazzi-phase5_5.sqlite3` — an existing SQLite Backup API copy at migration head `0007_similar_author_review_queue`; opened with SQLite `mode=ro` and `PRAGMA query_only=ON`.
- The legacy-path smoke failure was preserved as a tooling/database-state finding; the live database was not migrated.

## Baseline regression gates

- `python -m unittest discover -s tests -v`: **147 tests passed**, 52.290 s.
- `python scripts/validate_correspondence_pdf_sample.py`: **100 PDFs passed**, 0 parse errors, 0 fixture failures.
- Correct-head 25-paper smoke: completed read-only; 21 PDFs queued, 4 without reviewable primary PDF.

## Deterministic full-library scan

- Active papers scanned: **2513**.
- Reachable selected primary PDFs queued for mandatory AI review: **2060**.
- Papers without a reviewable primary PDF: **453**.
- Deterministic `PDF_PARSE_ERROR` flags: **0**.
- AI OCR-needed/image-only front matter: **16** (`430, 435, 439, 878, 939, 966, 981, 1111, 1137, 1321, 1430, 1591, 1601, 1605, 1639, 2267`).
- Deterministic selected supplementary document: **1**; paper IDs: `1793`.
- Multiple primary candidates: **65**; representative IDs: `168, 174, 177, 178, 180, 183, 189, 193 … (+57)`.
- Front-matter DOI conflicts: **30**; representative IDs: `503, 603, 841, 886, 898, 900, 905, 1074 … (+22)`.
- Low source-author header coverage: **166**.
- No reference section from deterministic parser: **224**.

### Deterministic risk distribution

| Severity | Papers |
|---|---:|
| P0 | 780 |
| P1 | 388 |
| P2 | 806 |
| P3 | 539 |

## Local-AI PDF review

- Every one of the 2060 queue rows was independently opened from its actual PDF. The review inspected front matter pages 1–3 and the tail needed for gross reference-section validation.
- Ground truth was not copied from `machine_predicted_corresponding_authors`; role decisions used PDF text, author-header locality, explicit correspondence wording, and narrowly scoped star/envelope conventions.
- Four read-only workers processed 515 queue rows each. Shards were merged and checked for exactly 2060 unique paper IDs.
- A first-pass marker rule was found to over-read dagger/body symbols; it was preserved as `ai_reviews_initial_pass.jsonl` in ignored validation data, then corrected. The final tracked `ai_reviews.jsonl` uses the narrower author-header-locality rule. This correction is documented rather than hidden.

| Review metric | Result |
|---|---:|
| Review rows present | 2060 / 2060 |
| REVIEWED | 1962 |
| UNRESOLVED | 98 |
| Ground truth EXPLICIT | 832 |
| Ground truth NONE_EXPLICIT | 1130 |
| Ground truth UNCERTAIN | 98 |

### Other AI quality checks

| Check | OK | BAD | UNCERTAIN | NOT_APPLICABLE |
|---|---:|---:|---:|---:|
| Primary document | 2035 | 23 | 2 | 0 |
| Text extraction | 2044 | 16 | 0 | 0 |
| Author header | 1888 | 56 | 98 | 18 |
| Reference section | 800 | 0 | 1250 | 10 |

- Primary selection BAD rows: `430, 435, 439, 476, 566, 567, 602, 939, 967, 981, 1111, 1137, 1321, 1430, 1499, 1591, 1601, 1605, 1639, 1793, 2133, 2208, 2267`.
- Text extraction BAD rows: `430, 435, 439, 878, 939, 966, 981, 1111, 1137, 1321, 1430, 1591, 1601, 1605, 1639, 2267`.
- Role wording with no unique source-author mapping: `188, 198, 252, 253, 260, 274, 295, 369, 375, 386, 402, 432, 443, 457, 478, 488, 489, 497, 552, 559, 603, 655, 658, 687, 698, 706, 872, 975, 976, 1052 … (+52)`.

## Correspondence score

| Metric | Value |
|---|---:|
| Scored papers | 1962 |
| TP | 272 |
| FP | 455 |
| FN | 1030 |
| Precision | 0.374140 |
| Recall | 0.208909 |
| Hard gate FP=0 | **FAIL** |
| Recall gate >=0.90 | **FAIL** |

Interpretation: the production resolver is materially over-inclusive for contact-only/marker signals and materially under-inclusive for publisher-specific or explicit multi-author correspondence layouts. The full correspondence population must remain blocked until a repair task and a new ground-truth review pass improve both gates.

## Recurring failure groups

### Publisher author-marker / star-envelope convention

- FN cases: 520; FN author assertions: 900.
- Representative paper IDs: `10, 11, 12, 13, 15, 17`.
- Root cause: the parser did not map a publisher-local star/envelope author marker to source mentions.

### Explicit role wording / email or named-author mapping

- FN cases: 109; FN author assertions: 130.
- Representative paper IDs: `107, 289, 400, 475, 480, 494`.
- Root cause: the parser did not preserve or map all explicit role-bearing names/emails in the PDF front matter.

### Contact-only and role overreach

- AI found `666` contact-only rows and `577` deterministic contact-only flags.
- The scorer reports **455** false-positive author assertions across **455** paper cases.
- Representative false-positive papers: `2, 4, 4, 4, 4, 4, 4, 4, 4, 6, 7, 8`.

## Every correspondence false positive

| Paper ID | False-positive source author | Ground-truth authors | Flags | Title |
|---:|---|---|---|---|
| 2 | David A. Kreplin | Hans-Joachim Werner, Peter J. Knowles | none | MCSCF optimization revisited. II. Combined first- and second-order orbital optimization for large molecules |
| 4 | Alexander Mitrushchenkov | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | Andreas Heßelmann | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | Daniel Kats | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | David A. Kreplin | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | Guntram Rauhut | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | Iakov Polyak | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | Joshua A. Black | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 4 | Marat Sibaev | Hans-Joachim Werner, Peter J. Knowles | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Molpro quantum chemistry package |
| 6 | Frank Glorius | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Energy transfer catalysis mediated by visible light: principles, applications, directions |
| 7 | Frank Glorius | NONE_EXPLICIT | none | Triplet Energy Transfer Photocatalysis: Unlocking the Next Level |
| 8 | Frank Glorius | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Energy transfer photocatalysis: exciting modes of reactivity |
| 96 | Long Wang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Conformational distortion-harnessed singlet fission dynamics in thienoquinoid: rapid generation and subsequent annihilation of multiexciton dark state |
| 98 | Ganglong Cui | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Selenium substitution effects on excited-state properties and photophysics of uracil: a MS-CASPT2 study |
| 98 | Xiang-Yang Liu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Selenium substitution effects on excited-state properties and photophysics of uracil: a MS-CASPT2 study |
| 100 | Xue-Ping Chang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Quantum mechanics/molecular mechanics studies on the mechanistic photophysics of sunscreen oxybenzone in methanol solution |
| 101 | Xue-Ping Chang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Quantum mechanics/molecular mechanics studies on the excited-state decay mechanisms of cytidine aza-analogues: 5-azacytidine and 2′-deoxy-5-azacytidine in aqueous solution |
| 102 | Xue-Ping Chang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Quantum mechanics/molecular mechanics studies on mechanistic photophysics of cytosine aza-analogues: 2,4-diamino-1,3,5-triazine and 2-amino-1,3,5-triazine in aqueous solution |
| 103 | Xue-Ping Chang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Quantum mechanics/molecular mechanics studies on excited state decay pathways of 5-azacytosine in aqueous solution |
| 104 | Bin-Bin Xie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | MS-CASPT2 studies on the mechanistic photophysics of tellurium-substituted guanine and cytosine |
| 104 | Ganglong Cui | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | MS-CASPT2 studies on the mechanistic photophysics of tellurium-substituted guanine and cytosine |
| 111 | Jiexiang Xia | Yun-Fang Yang, Yuanbin She | none | Porous organic polymers with shiftable active Co(II) sites for photocatalytic reduction of CO2 to C2H4 |
| 112 | Long Wang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Side-chain ionization enables ultrafast intramolecular singlet fission in the azaquinodimethane skeleton |
| 112 | Teng-Shuo Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Side-chain ionization enables ultrafast intramolecular singlet fission in the azaquinodimethane skeleton |
| 112 | Yi Liu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Side-chain ionization enables ultrafast intramolecular singlet fission in the azaquinodimethane skeleton |
| 114 | Keke Wang | Yun-Fang Yang, Yuanbin She | none | Hydrogen-Bonded organic framework Containing stacked Cu2+ for photocatalytic reduction of CO2 to C2H4 |
| 115 | Long Wang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Efficient singlet fission in rubicene null aggregates |
| 115 | Teng-Shuo Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Efficient singlet fission in rubicene null aggregates |
| 171 | Shirin Faraji | NONE_EXPLICIT | none | Singlet fission in tetracene: an excited state analysis |
| 173 | Matthew Y. Sfeir | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet fission in a hexacene dimer: energetics dictate dynamics |
| 180 | Victor Gray | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Recent advances in triplet-triplet annihilation upconversion and singlet fission, towards solar energy applications |
| 183 | Sebastian Paeckel | Sam Mardazad | MULTIPLE_PRIMARY_CANDIDATES, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Quantum dynamics simulation of intramolecular singlet fission in covalently linked tetracene dimer |
| 186 | Gregory D. Scholes | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photophysical characterization and time-resolved spectroscopy of a anthradithiophene dimer: exploring the role of conformation in singlet fission |
| 189 | Haibo Ma | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Optimizing through-space interaction for singlet fission by using macrocyclic structures |
| 193 | Hyungjun Kim | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Multiexcitonic Triplet Pair Generation in Oligoacene Dendrimers as Amorphous Solid-State Miniatures |
| 210 | Michael R. Wasielewski | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Influence of the heavy-atom effect on singlet fission: a study of platinum-bridged pentacene dimers |
| 214 | Heyuan Liu | Chunfeng Zhang, Haibo Ma | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Free-triplet generation with improved efficiency in tetracene oligomers through spatially separated triplet pair states |
| 214 | Xiaoyu Xie | Chunfeng Zhang, Haibo Ma | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Free-triplet generation with improved efficiency in tetracene oligomers through spatially separated triplet pair states |
| 214 | Zhiwei Wang | Chunfeng Zhang, Haibo Ma | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Free-triplet generation with improved efficiency in tetracene oligomers through spatially separated triplet pair states |
| 221 | Felix Plasser | NONE_EXPLICIT | none | Exciton analysis of many-body wave functions: bridging the gap between the quasiparticle and molecular orbital pictures |
| 226 | Yasuhiro Kobori | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Electron spin polarization generated by transport of singlet and quintet multiexcitons to spin-correlated triplet pairs during singlet fissions |
| 241 | Marc A. Baldo | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | A transferable model for singlet-fission kinetics |
| 248 | Denis Jacquemin | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | TD-DFT benchmarks: a review |
| 267 | Heyuan Liu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Tuning singlet fission in amphipathic tetracene nanoparticles by controlling the molecular packing with side-group engineering |
| 267 | Xiyou Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Tuning singlet fission in amphipathic tetracene nanoparticles by controlling the molecular packing with side-group engineering |
| 278 | Gregor Witte | Sangam Chatterjee | none | Molecular packing determines singlet exciton fission in organic semiconductors |
| 284 | Luis M. Campos | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Intramolecular singlet fission in oligoacene heterodimers |
| 285 | Michael R. Wasielewski | NONE_EXPLICIT | none | Charge-transfer character in a covalent diketopyrrolopyrrole dimer: implications for singlet fission |
| 287 | Justin C. Johnson | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Dynamics of singlet fission and electron injection in self-assembled acene monolayers on titanium dioxide |
| 294 | Daniele Fazzi | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | A computational investigation on singlet and triplet exciton couplings in acene molecular crystals |
| 337 | R. Mitric | F. Santoro | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Predicting fluorescence quantum yields for molecules in solution: A critical assessment of the harmonic approximation and the choice of the lineshape function |
| 351 | Aurora Ponzi | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Photoionization observables from multi-reference dyson orbitals coupled to B-spline DFT and TD-DFT continuum |
| 351 | Piero Decleva | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Photoionization observables from multi-reference dyson orbitals coupled to B-spline DFT and TD-DFT continuum |
| 352 | Markus Reiher | NONE_EXPLICIT | none | New approaches for ab initio calculations of molecules with strong electron correlation |
| 352 | Stefan Knecht | NONE_EXPLICIT | none | New approaches for ab initio calculations of molecules with strong electron correlation |
| 395 | Markus Reiher | NONE_EXPLICIT | none | Spin-adapted matrix product states and operators |
| 395 | Sebastian Keller | NONE_EXPLICIT | none | Spin-adapted matrix product states and operators |
| 396 | Markus Reiher | NONE_EXPLICIT | none | An efficient matrix product operator representation of the quantum chemical hamiltonian |
| 396 | Matthias Troyer | NONE_EXPLICIT | none | An efficient matrix product operator representation of the quantum chemical hamiltonian |
| 396 | Sebastian Keller | NONE_EXPLICIT | none | An efficient matrix product operator representation of the quantum chemical hamiltonian |
| 528 | Laura Gagliardi | Kristine Pierloot | none | Multiconfigurational second-order perturbation theory restricted active space (RASPT2) method for electronic excited states: a benchmark study |
| 529 | Keiji Morokuma | Koichi Ohno | none | Updated branching plane for finding conical intersections without coupling derivative vectors |
| 564 | Martin Head-Gordon | NONE_EXPLICIT | none | Characterizing unpaired electrons from the one-particle density matrix |
| 652 | Felix Plasser | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Statistical analysis of electronic excitation processes: spatial location, compactness, charge transfer, and electron-hole correlation |
| 657 | Steven Vancoillie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Calculation of EPR g tensors for transition‐metal complexes based on multiconfigurational perturbation theory (CASPT2) |
| 670 | Haibo Ma | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Describing dynamic electron correlation beyond a large active space |
| 671 | Haibo Ma | NONE_EXPLICIT | none | Theoretical investigation of singlet fission processes in organic photovoltaics |
| 671 | Xiaoyu Xie | NONE_EXPLICIT | none | Theoretical investigation of singlet fission processes in organic photovoltaics |
| 691 | Anna I. Krylov | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | On couplings and excimers: lessons from studies of singlet fission in covalently linked tetracene dimers |
| 693 | Josef Michl | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet fission: optimization of chromophore dimer geometry |
| 694 | Yoshiyasu Matsumoto | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Coherent singlet fission activated by symmetry breaking |
| 696 | Murad J. Y. Tayebjee | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Quintet multiexciton dynamics in singlet fission |
| 699 | Ilme Schlichting | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Chromophore twisting in the excited state of a photoswitchable fluorescent protein captured by time-resolved serial femtosecond crystallography |
| 699 | Jacques-Philippe Colletier | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Chromophore twisting in the excited state of a photoswitchable fluorescent protein captured by time-resolved serial femtosecond crystallography |
| 699 | Martin Weik | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Chromophore twisting in the excited state of a photoswitchable fluorescent protein captured by time-resolved serial femtosecond crystallography |
| 703 | Stephen R. Meech | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Infrared spectroscopy reveals multi-step multi-timescale photoactivation in the photoconvertible protein archetype dronpa |
| 708 | Bin-Bin Xie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Theoretical studies on photo-induced cycloaddition and (6-4) reactions of the thymidine:4-thiothymidine dimer in a DNA duplex |
| 714 | Martin T. Zanni | NONE_EXPLICIT | none | Impact of non-equilibrium molecular packings on singlet fission in microcrystals observed using 2D white-light microscopy |
| 724 | Dominik Munz | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet Fission in Carbene-Derived Diradicaloids |
| 728 | Ilme Schlichting | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Photoswitching mechanism of a fluorescent protein revealed by time-resolved crystallography and transient absorption spectroscopy |
| 728 | Michel Sliwa | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Photoswitching mechanism of a fluorescent protein revealed by time-resolved crystallography and transient absorption spectroscopy |
| 732 | Jan Freudenberg | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | TIPS-Ethynylated Naphthodiquinoline and Naphthodiacridine: Novel Diazabisacenes |
| 733 | Chad Risko | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Nanoribbons or weakly connected acenes? The influence of pyrene insertion on linearly extended ring systems |
| 733 | John E. Anthony | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Nanoribbons or weakly connected acenes? The influence of pyrene insertion on linearly extended ring systems |
| 742 | Ganglong Cui | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Hydrogen-Bond Network Determines the Early Photoisomerization Processes of Cph1 and AnPixJ Phytochromes |
| 749 | David Casanova | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Doubly Excited State in Singlet Fission |
| 750 | Heinrich Schwoerer | Hélène Seiler, Mariana Rossi, Sebastian Hammer | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Nuclear dynamics of singlet exciton fission in pentacene single crystals |
| 754 | Dominik Munz | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Unconventional singlet fission materials |
| 754 | Tobias Ullrich | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Unconventional singlet fission materials |
| 760 | Dominique Bourgeois | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Rational Control of Off‐State Heterogeneity in a Photoswitchable Fluorescent Protein Provides Switching Contrast Enhancement** |
| 760 | Tatiana Domratcheva | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Rational Control of Off‐State Heterogeneity in a Photoswitchable Fluorescent Protein Provides Switching Contrast Enhancement** |
| 763 | Claudia Climent | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Not dark yet for strong light-matter coupling to accelerate singlet fission dynamics |
| 768 | C. De Graaf | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | On the role of dynamic electron correlation in non-orthogonal configuration interaction with fragments |
| 768 | C. Sousa | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | On the role of dynamic electron correlation in non-orthogonal configuration interaction with fragments |
| 769 | Takeharu Nagai | NONE_EXPLICIT | none | Extension of the short wavelength side of fluorescent proteins using hydrated chromophores, and its application |
| 779 | Jan Freudenberg | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Etheno-bridged Azaacene Spiro Dimers |
| 783 | Jiawen Chen | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Synthesis, Characterization and Singlet Fission Behaviors of Heteroatom-Doped Polycyclic Aromatic Hydrocarbons with (beta, beta) Connected Furan/Thiophene Ring |
| 787 | Taku Hasobe | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Control of intramolecular singlet fission in a pentacene dimer by hydrostatic pressure |
| 802 | Todd J. Martínez | Nanna H. List | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Chemical control of excited-state reactivity of the anionic green fluorescent protein chromophore |
| 812 | Barbara Marchetti | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Modeling the unimolecular decay dynamics of the fluorinated criegee intermediate, CF3CHOO |
| 812 | Ernest Antwi | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Modeling the unimolecular decay dynamics of the fluorinated criegee intermediate, CF3CHOO |
| 819 | Ruibin Liang | NONE_EXPLICIT | none | Unraveling solvent and substituent effects in the photodynamics of light‐dependent microtubule inhibitors for cancer phototherapy |
| 831 | Mariusz Pietrzak | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Light-induced selectivity in an exemplary photodimerization reaction of varied azaanthracenes |
| 831 | Tomasz Ratajczyk | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Light-induced selectivity in an exemplary photodimerization reaction of varied azaanthracenes |
| 832 | Joanna Jankowska | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photo-oxidation of methanol in complexes with pyrido[2,3- <i>b</i> ]pyrazine: a nonadiabatic molecular dynamics study |
| 836 | Inés Corral | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photophysical characterization of isoguanine in a prebiotic‐like environment |
| 841 | Stephen R. Meech | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, FRONT_MATTER_DOI_CONFLICT | Complex multistate photophysics of a rhodanine photoswitch |
| 861 | Martin Head-Gordon | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Spin–flip non-orthogonal configuration interaction: a variational and almost black-box method for describing strongly correlated molecules |
| 875 | Mario Barbatti | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | On the short and long phosphorescence lifetimes of aromatic carbonyls |
| 875 | Saikat Mukherjee | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | On the short and long phosphorescence lifetimes of aromatic carbonyls |
| 876 | Anjay Manian | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | A first principles examination of phosphorescence |
| 910 | Ralph Ernstorfer | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, NO_REFERENCE_SECTION, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Orbital-resolved observation of singlet fission |
| 914 | Heyuan Liu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Intramolecular singlet fission and triplet exciton harvesting in tetracene oligomers for solar energy conversion |
| 914 | Xiyou Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Intramolecular singlet fission and triplet exciton harvesting in tetracene oligomers for solar energy conversion |
| 932 | Ganglong Cui | NONE_EXPLICIT | none | Challenges and opportunities in electronic structure theory |
| 932 | Xiangjian Shen | NONE_EXPLICIT | none | Challenges and opportunities in electronic structure theory |
| 963 | WanZhen Liang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Charge transfer in organic molecules for solar cells: theoretical perspective |
| 963 | Yi Zhao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Charge transfer in organic molecules for solar cells: theoretical perspective |
| 984 | Andrew J. Musser | NONE_EXPLICIT | none | Tracking ultrafast reactions in organic materials through vibrational coherence: vibronic coupling mechanisms in singlet fission |
| 985 | Thomas T. M. Palstra | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Polymorphism in pentacene |
| 993 | Ganglong Cui | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | QM and ONIOM studies on thermally activated delayed fluorescence of copper( <span style="font-variant:small-caps;">i</span> ) complexes in gas phase, solution, and crystal |
| 1042 | Margherita Maiuri | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, MULTIPLE_PRIMARY_CANDIDATES | Singlet Heterofission in Tetracene–Pentacene Thin‐Film Blends |
| 1044 | Stefan Jakobs | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Coordinate-Targeted and Coordinate-Stochastic Super-Resolution Microscopy with the Reversibly Switchable Fluorescent Protein Dreiklang |
| 1044 | Stefan W. Hell | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Coordinate-Targeted and Coordinate-Stochastic Super-Resolution Microscopy with the Reversibly Switchable Fluorescent Protein Dreiklang |
| 1047 | Zhen Huang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Biochemistry of Selenium‐Derivatized Naturally Occurring and Unnatural Nucleic Acids |
| 1050 | Xiaowei Zhuang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Multicolor Super-Resolution Fluorescence Imaging via Multi-Parameter Fluorophore Detection |
| 1057 | Piotr Petelenz | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Dopant-Catalyzed Singlet Exciton Fission |
| 1068 | Lorenzo Mangolini | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Bidirectional triplet exciton transfer between silicon nanocrystals and perylene |
| 1068 | Sean T. Roberts | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Bidirectional triplet exciton transfer between silicon nanocrystals and perylene |
| 1077 | Rifka Vlijm | NONE_EXPLICIT | none | Fluorescence-based super-resolution-microscopy strategies for chromatin studies |
| 1080 | Jiun-Haw Lee | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | High-Performance Deep-Blue OLEDs Harnessing Triplet-Triplet Annihilation Under Low Dopant Concentration |
| 1083 | Qun Xu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Porphyrin-based Bi-MOFs with Enriched Surface Bi Active Sites for Boosting Photocatalytic CO2 Reduction |
| 1083 | Xiaoli Zheng | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Porphyrin-based Bi-MOFs with Enriched Surface Bi Active Sites for Boosting Photocatalytic CO2 Reduction |
| 1088 | Weiqiao Deng | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Flavanthrene derivatives as photostable and efficient singlet exciton fission materials |
| 1088 | Wenping Hu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Flavanthrene derivatives as photostable and efficient singlet exciton fission materials |
| 1096 | Zhen Huang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Selenium Derivatization of Nucleic Acids for X‐Ray Crystal‐Structure and Function Studies |
| 1100 | Vladislav V. Verkhusha | NONE_EXPLICIT | none | Red Fluorescent Proteins: Advanced Imaging Applications and Future Design |
| 1102 | Nathan C. Shaner | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Aequorea's secrets revealed: New fluorescent proteins with unique properties for bioimaging and biosensing |
| 1108 | Nobuhiro Yanai | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Porous film impregnation method for record-efficiency visible-to-UV photon upconversion and subsolar light harvesting |
| 1116 | Peter Karran | NONE_EXPLICIT | none | Photoactivation of DNA thiobases as a potential novel therapeutic option |
| 1119 | Stefan Jakobs | NONE_EXPLICIT | none | RESOLFT Nanoscopy of Fixed Cells Using a Z-Domain Based Fusion Protein for Labelling |
| 1124 | Nadia Rega | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | On the optical absorption of the anionic GFP chromophore in vacuum, solution, and protein |
| 1126 | Karl Leo | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Highly Crystalline Rubrene Light-Emitting Diodes with Epitaxial Growth |
| 1126 | Shu-Jen Wang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Highly Crystalline Rubrene Light-Emitting Diodes with Epitaxial Growth |
| 1136 | Michael R. Hamblin | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photodynamic therapy: a new antimicrobial approach to infectious disease? |
| 1139 | Karolis Kazlauskas | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Boost in Solid-State Photon Upconversion Efficiency through Combined Approach of Melt-Processing and Purification |
| 1143 | Hongwei Hou | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Guest-Induced Multilevel Charge Transport Strategy for Developing Metal-Organic Frameworks to Boost Photocatalytic CO2 Reduction |
| 1143 | Jie Wu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Guest-Induced Multilevel Charge Transport Strategy for Developing Metal-Organic Frameworks to Boost Photocatalytic CO2 Reduction |
| 1143 | Zhichao Shao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Guest-Induced Multilevel Charge Transport Strategy for Developing Metal-Organic Frameworks to Boost Photocatalytic CO2 Reduction |
| 1144 | Katharina Landfester | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | One-pot fabrication of amphiphilic photoswitchable thiophene-based fluorescent polymer dots |
| 1144 | Ulrich Ziener | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | One-pot fabrication of amphiphilic photoswitchable thiophene-based fluorescent polymer dots |
| 1147 | Feng-Ming Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Integrating Enrichment, Reduction, and Oxidation Sites in One System for Artificial Photosynthetic Diluted CO2 Reduction |
| 1149 | Hongbing Fu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Intramolecular Singlet Fission in an Antiaromatic Polycyclic Hydrocarbon |
| 1151 | Debashree Ghosh | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet-triplet gaps in polyacenes: a delicate balance between dynamic and static correlations investigated by spin-flip methods |
| 1156 | Taku Hasobe | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Torsional Motion Effect on the Quintet Multiexciton Formation through Intramolecular Singlet Fission in Ferrocene-Bridged Pentacene Dimers |
| 1156 | Yasuhiro Kobori | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Torsional Motion Effect on the Quintet Multiexciton Formation through Intramolecular Singlet Fission in Ferrocene-Bridged Pentacene Dimers |
| 1159 | Walter Thiel | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Concerted Asynchronous Hula‐Twist Photoisomerization in the S65T/H148D Mutant of Green Fluorescent Protein |
| 1159 | Xuebo Chen | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Concerted Asynchronous Hula‐Twist Photoisomerization in the S65T/H148D Mutant of Green Fluorescent Protein |
| 1176 | Juyoung Yoon | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Intracellular Modulation of Excited‐State Dynamics in a Chromophore Dyad: Differential Enhancement of Photocytotoxicity Targeting Cancer Cells |
| 1183 | Jun Yang | NONE_EXPLICIT | none | Exploring optimal multimode vibronic pathways in singlet fission of azaborine analogues of perylene |
| 1186 | Isabell Theves | NONE_EXPLICIT | none | Tracing the Photoaddition of Pharmaceutical Psoralens to DNA |
| 1186 | Janina Diekmann | NONE_EXPLICIT | none | Tracing the Photoaddition of Pharmaceutical Psoralens to DNA |
| 1186 | Peter Gilch | NONE_EXPLICIT | none | Tracing the Photoaddition of Pharmaceutical Psoralens to DNA |
| 1189 | Nobuhiro Yanai | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Discovery of Key TIPS-Naphthalene for Efficient Visible-to-UV Photon Upconversion under Sunlight and Room Light** |
| 1193 | Roland Mitric | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Effect of varying the TD-lc-DFTB range-separation parameter on charge and energy transfer in a model pentacene/buckminsterfullerene heterojunction |
| 1193 | Xincheng Miao | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Effect of varying the TD-lc-DFTB range-separation parameter on charge and energy transfer in a model pentacene/buckminsterfullerene heterojunction |
| 1203 | Angelo Giussani | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photoinduced formation mechanism of the thymine–thymine (6–4) adduct in DNA; a QM(CASPT2//CASSCF):MM(AMBER) study |
| 1205 | Hideaki Mizuno | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Excited state dynamics of the photoconvertible fluorescent protein Kaede revealed by ultrafast spectroscopy |
| 1215 | Philipp Kukura | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Evidence for conical intersection dynamics mediating ultrafast singlet exciton fission |
| 1217 | T. Lasser | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Combined multi-plane phase retrieval and super-resolution optical fluctuation imaging for 4D cell microscopy |
| 1224 | Stefan Jakobs | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Two-Color RESOLFT Nanoscopy with Green and Red Fluorescent Photochromic Proteins |
| 1224 | Stefan W. Hell | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Two-Color RESOLFT Nanoscopy with Green and Red Fluorescent Photochromic Proteins |
| 1226 | Chong Fang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Excited State Structural Evolution of a GFP Single-Site Mutant Tracked by Tunable Femtosecond-Stimulated Raman Spectroscopy |
| 1226 | Liangdong Zhu | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Excited State Structural Evolution of a GFP Single-Site Mutant Tracked by Tunable Femtosecond-Stimulated Raman Spectroscopy |
| 1226 | Longteng Tang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Excited State Structural Evolution of a GFP Single-Site Mutant Tracked by Tunable Femtosecond-Stimulated Raman Spectroscopy |
| 1226 | Miles A. Taylor | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Excited State Structural Evolution of a GFP Single-Site Mutant Tracked by Tunable Femtosecond-Stimulated Raman Spectroscopy |
| 1226 | Yanli Wang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Excited State Structural Evolution of a GFP Single-Site Mutant Tracked by Tunable Femtosecond-Stimulated Raman Spectroscopy |
| 1231 | Ilaria Testa | NONE_EXPLICIT | none | Predicting resolution and image quality in RESOLFT and other point scanning microscopes [Invited] |
| 1234 | Jianzhang Zhao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Recent progress in heavy atom-free organic compounds showing unexpected intersystem crossing (ISC) ability |
| 1235 | Kangmin He | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Single-molecule imaging and tracking of molecular dynamics in living cells |
| 1235 | Xiaohong Fang | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Single-molecule imaging and tracking of molecular dynamics in living cells |
| 1239 | William Barford | NONE_EXPLICIT | none | Theory of the dark state of polyenes and carotenoids |
| 1240 | Kenji Kamada | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Kinetics of photon upconversion by triplet-triplet annihilation: a comprehensive tutorial |
| 1240 | Yoichi Murakami | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Kinetics of photon upconversion by triplet-triplet annihilation: a comprehensive tutorial |
| 1242 | Josef Michl | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Optimal Arrangements of Tetracene Molecule Pairs for Fast Singlet Fission |
| 1250 | Jiro Abe | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Fluorescence modulation by fast photochromism of a [2.2]paracyclophane-bridged imidazole dimer possessing a perylene bisimide moiety |
| 1254 | Fude Feng | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | GSH and H <sub>2</sub> O <sub>2</sub> Co‐Activatable Mitochondria‐Targeted Photodynamic Therapy under Normoxia and Hypoxia |
| 1254 | Shu Wang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | GSH and H <sub>2</sub> O <sub>2</sub> Co‐Activatable Mitochondria‐Targeted Photodynamic Therapy under Normoxia and Hypoxia |
| 1257 | Xiyou Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Efficient singlet fission in nanoparticles of amphipathic anthracene-tetracene dyad with broadband light harvesting ability |
| 1261 | Jiwoong Kwon | NONE_EXPLICIT | none | Enhanced UnaG With Minimal Labeling Artifact for Single-Molecule Localization Microscopy |
| 1264 | Pablo Rivera-Fuentes | NONE_EXPLICIT | NO_REFERENCE_SECTION | Photochemically Active Dyes for Super-Resolution Microscopy |
| 1266 | Piotr Petelenz | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Lowest Singlet Exciton in Pentacene: Modern Calculations versus Classic Experiments |
| 1271 | Ganglong Cui | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | A theoretical study of the light-induced cross-linking reaction of 5-fluoro-4-thiouridine with thymine |
| 1280 | Yuttapoom Puttisong | NONE_EXPLICIT | none | Competition between triplet pair formation and excimer-like recombination controls singlet fission yield |
| 1286 | Yu Xie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Study of the exciton dynamics in perylene bisimide (PBI) aggregates with symmetrical quasiclassical dynamics based on the Meyer-Miller mapping Hamiltonian |
| 1290 | Takahiro Teramoto | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Revealing ultrafast vibronic dynamics of tetracene molecules with sub-8 fs UV impulsive Raman spectroscopy |
| 1304 | Guijie Liang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Triplet energy migration pathways from PbS quantum dots to surface-anchored polyacenes controlled by charge transfer |
| 1304 | Kaifeng Wu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Triplet energy migration pathways from PbS quantum dots to surface-anchored polyacenes controlled by charge transfer |
| 1310 | Robert E. Campbell | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Engineering Photosensory Modules of Non-Opsin-Based Optogenetic Actuators |
| 1310 | Yi Shen | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Engineering Photosensory Modules of Non-Opsin-Based Optogenetic Actuators |
| 1318 | Alexander S. Mishin | NONE_EXPLICIT | none | Fast reversibly photoswitching red fluorescent proteins for live-cell RESOLFT nanoscopy |
| 1318 | Ilaria Testa | NONE_EXPLICIT | none | Fast reversibly photoswitching red fluorescent proteins for live-cell RESOLFT nanoscopy |
| 1346 | Kazuya Kikuchi | NONE_EXPLICIT | none | Photostable and photoswitching fluorescent dyes for super-resolution imaging |
| 1351 | Wenfeng Jiang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Polymeric Unimolecular CO Dehydrogenase Mimic with both Inner and Outer Spheres for Enhanced Photocatalytic CO2 Reduction in Aqueous Solution |
| 1354 | Tian Tian | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Chemical Control of CRISPR Gene Editing via Conditional Diacylation Crosslinking of Guide RNAs |
| 1367 | Cheng Chen | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Photogrammetry of Ultrafast Excited-State Intramolecular Proton Transfer Pathways in the Fungal Pigment Draconin Red |
| 1367 | Chong Fang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Photogrammetry of Ultrafast Excited-State Intramolecular Proton Transfer Pathways in the Fungal Pigment Draconin Red |
| 1369 | Rui Cao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Across the Board: Rui Cao on Electrocatalytic CO2 Reduction |
| 1370 | Rui Liu | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Insights into the Binding of Red Fluorescent Protein mCherry-Specific Nanobodies |
| 1370 | Yu Ding | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Insights into the Binding of Red Fluorescent Protein mCherry-Specific Nanobodies |
| 1375 | Toshiko Mizokuro | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Molecular arrangement in diphenylanthracene derivative films deposited under vacuum on in-plane oriented polythiophene films |
| 1383 | Mauro Gemmi | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | 3D Electron Diffraction Structure Determination of Terrylene, a Promising Candidate for Intermolecular Singlet Fission |
| 1388 | Yi Xie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Excitonic Effects in Polymeric Photocatalysts |
| 1395 | Marcus Scheele | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Prospects of Coupled Organic-Inorganic Nanostructures for Charge and Energy Transfer Applications |
| 1396 | P. James Schuck | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, NO_REFERENCE_SECTION, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Indefinite and bidirectional near-infrared nanocrystal photoswitching |
| 1396 | Yung Doug Suh | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, NO_REFERENCE_SECTION, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Indefinite and bidirectional near-infrared nanocrystal photoswitching |
| 1400 | Xianghong Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Achieving efficient photodynamic therapy under both normoxia and hypoxia using cyclometalated Ru( <span style="font-variant:small-caps;">ii</span> ) photosensitizer through type I photochemical process |
| 1404 | Alessandro Troisi | NONE_EXPLICIT | none | Singlet fission in linear chains of molecules |
| 1404 | Francesco Ambrosio | NONE_EXPLICIT | none | Singlet fission in linear chains of molecules |
| 1414 | Liang Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Porphyrins-Assisted Cocatalyst Engineering with Co-O-V Bond in BiVO4 Photoanode for Efficient Oxygen Evolution Reaction |
| 1431 | Justin C. Johnson | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Polymorphism influences singlet fission rates in tetracene thin films |
| 1440 | Marc Beyer | Daniel Humme | none | Systematic review of combination therapies for mycosis fungoides |
| 1440 | Ricardo Erdmann | Daniel Humme | none | Systematic review of combination therapies for mycosis fungoides |
| 1443 | Alia Tadjer | NONE_EXPLICIT | none | Women in the Singlet Fission World: Pearls in a Semi-Open Shell |
| 1443 | Joanna Stoycheva | NONE_EXPLICIT | none | Women in the Singlet Fission World: Pearls in a Semi-Open Shell |
| 1450 | Luis M. Campos | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Direct Exciton Harvesting from a Bound Triplet Pair |
| 1450 | Matthew Y. Sfeir | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Direct Exciton Harvesting from a Bound Triplet Pair |
| 1458 | Mark Prescott | NONE_EXPLICIT | none | Phanta: A Non-Fluorescent Photochromic Acceptor for pcFRET |
| 1459 | Lucas O. Wagner | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | DFT in a nutshell |
| 1460 | James H. Geiger | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | A Photoisomerizing Rhodopsin Mimic Observed at Atomic Resolution |
| 1462 | Antonios M. Alvertis | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Impact of exciton delocalization on exciton-vibration interactions in organic semiconductors |
| 1463 | Tomoki Matsuda | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Fluorescent Protein-Based Indicators for Functional Super-Resolution Imaging of Biomolecular Activities in Living Cells |
| 1471 | Alexander Gerlach | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Pentacene/perfluoropentacene bilayers on Au(111) and Cu(111): impact of organic-metal coupling strength on molecular structure formation |
| 1472 | Gagik G. Gurzadyan | NONE_EXPLICIT | none | Ultrafast spectroscopy reveals singlet fission, ionization and excimer formation in perylene film |
| 1477 | Benedetta Mennucci | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Excited state characterization of carbonyl containing carotenoids: a comparison between single and multireference descriptions |
| 1477 | Riccardo Spezia | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Excited state characterization of carbonyl containing carotenoids: a comparison between single and multireference descriptions |
| 1477 | Stefan Knecht | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Excited state characterization of carbonyl containing carotenoids: a comparison between single and multireference descriptions |
| 1486 | Maurizio Persico | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Nonadiabatic dynamics simulations of singlet fission in 2,5-bis(fluorene-9-ylidene)-2,5-dihydrothiophene crystals |
| 1488 | F. J. Child | NONE_EXPLICIT | ROLE_SIGNAL_WITHOUT_EMAIL | A randomized cross-over study to compare PUVA and extracorporeal photopheresis in the treatment of plaque stage (T2) mycosis fungoides |
| 1492 | Juyoung Yoon | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Molecular Design of Highly Efficient Heavy‐Atom‐Free Triplet BODIPY Derivatives for Photodynamic Therapy and Bioimaging |
| 1492 | Sungnam Park | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Molecular Design of Highly Efficient Heavy‐Atom‐Free Triplet BODIPY Derivatives for Photodynamic Therapy and Bioimaging |
| 1494 | Djemel Hamdane | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Ultrafast photoinduced flavin dynamics in the unusual active site of the tRNA methyltransferase TrmFO |
| 1494 | Pascal Plaza | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Ultrafast photoinduced flavin dynamics in the unusual active site of the tRNA methyltransferase TrmFO |
| 1496 | Chong Fang | NONE_EXPLICIT | none | Delineating Ultrafast Structural Dynamics of a Green-Red Fluorescent Protein for Calcium Sensing |
| 1506 | CW Machan | NONE_EXPLICIT | none | Secondary-Sphere Effects in Molecular Electrocatalytic CO2 Reduction |
| 1508 | Joerg Bewersdorf | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Determination of two-photon photoactivation rates of fluorescent proteins |
| 1523 | Dassia Egorova | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Real-time observation of multiexcitonic states in ultrafast singlet fission using coherent 2D electronic spectroscopy |
| 1524 | Liming Nie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Reactive oxygen species generating systems meeting challenges of photodynamic cancer therapy |
| 1540 | Bruno Therrien | Lucienne Juillerat-Jeanneret | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Ruthenium Porphyrin Compounds for Photodynamic Therapy of Cancer |
| 1546 | W. Barford | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Higher-energy triplet-pair states in polyenes and their role in intramolecular singlet fission |
| 1550 | Oliver Griesbeck | NONE_EXPLICIT | none | Imaging-Based Screening Platform Assists Protein Engineering |
| 1556 | Eric Vauthey | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Tuning symmetry breaking charge separation in perylene bichromophores by conformational control |
| 1557 | Ping Lu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Observation of Vibrational Phosphorescence Peaks at Room Temperature and Their Impacts on Triplet-Triplet Annihilation |
| 1579 | Donald G. Truhlar | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Electronic spectrum and characterization of diabatic potential energy surfaces for thiophenol |
| 1579 | Shaozeng Sun | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Electronic spectrum and characterization of diabatic potential energy surfaces for thiophenol |
| 1583 | Man Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Deciphering the Selectivity of the Electrochemical CO <sub>2</sub> Reduction to CO by a Cobalt Porphyrin Catalyst in Neutral Aqueous Solution: Insights from DFT Calculations |
| 1589 | Cristina Puzzarini | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, FRONT_MATTER_DOI_CONFLICT | Accurate molecular structure and spectroscopic properties of nucleobases: a combined computational–microwave investigation of 2-thiouracil as a case study |
| 1595 | Purshotam Sharma | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Can modified DNA base pairs with chalcogen bonding expand the genetic alphabet? A combined quantum chemical and molecular dynamics simulation study |
| 1599 | Susanne Ullrich | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | 2-Thiouracil intersystem crossing photodynamics studied by wavelength-dependent photoelectron and transient absorption spectroscopies |
| 1610 | Giuseppe Trigiante | NONE_EXPLICIT | none | Topical 4-thiothymidine is a viable photosensitiser for the photodynamic therapy of skin malignancies |
| 1612 | Domenica Farci | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photophysics of deinoxanthin, the keto-carotenoid bound to the main S-layer unit of Deinococcus radiodurans |
| 1615 | Tim Kowalczyk | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Acene-linked covalent organic frameworks as candidate materials for singlet fission |
| 1628 | Ally Aukauloo | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Dissection of Light‐Induced Charge Accumulation at a Highly Active Iron Porphyrin: Insights in the Photocatalytic CO <sub>2</sub> Reduction |
| 1628 | Zakaria Halime | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Dissection of Light‐Induced Charge Accumulation at a Highly Active Iron Porphyrin: Insights in the Photocatalytic CO <sub>2</sub> Reduction |
| 1630 | Alessio Petrone | NONE_EXPLICIT | none | A Not Obvious Correlation Between the Structure of Green Fluorescent Protein Chromophore Pocket and Hydrogen Bond Dynamics: A Choreography From ab initio Molecular Dynamics |
| 1631 | Andreas Dreuw | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | High-Resolution Electronic Excitation and Emission Spectra of Pentacene and 6,13-Diazapentacene Monomers and Weakly Bound Dimers by Matrix-Isolation Spectroscopy |
| 1646 | Roger Y. Tsien | NONE_EXPLICIT | none | Autofluorescent Proteins with Excitation in the Optical Window for Intravital Imaging in Mammals |
| 1647 | Yang Zhao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet fission dynamics and optical spectra of pentacene and its derivatives |
| 1661 | Hailang Dai | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Monitoring Various Bioactivities at the Molecular, Cellular, Tissue, and Organism Levels via Biological Lasers |
| 1666 | Theo Lasser | NONE_EXPLICIT | none | SOFI Simulation Tool: A Software Package for Simulating and Testing Super-Resolution Optical Fluctuation Imaging |
| 1677 | Frank Schreiber | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Efficient Energy Transfer and Singlet Fission in Co-Deposited Thin Films of Pentacene and Anthradithiophene |
| 1677 | Marina Gerhard | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Efficient Energy Transfer and Singlet Fission in Co-Deposited Thin Films of Pentacene and Anthradithiophene |
| 1678 | Gregor P. C. Drummen | Hellen C. Ishikawa-Ankerhold | none | Advanced Fluorescence Microscopy Techniques-FRAP, FLIP, FLAP, FRET and FLIM |
| 1679 | Maryam Souri | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Investigation of solvent effect on adenine-thymine base pair interaction |
| 1680 | Hongbing Fu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Revealing the Nature of Singlet Fission under the Veil of Internal Conversion |
| 1680 | Shuming Bai | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Revealing the Nature of Singlet Fission under the Veil of Internal Conversion |
| 1681 | Bern Kohler | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Life in the light: nucleic acid photoproperties as a legacy of chemical evolution |
| 1681 | Mattanjah S. De Vries | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Life in the light: nucleic acid photoproperties as a legacy of chemical evolution |
| 1683 | Chenglin Zhou | Yue Zhang, Mei Lin | none | Enzyme-catalyzed electrochemical aptasensor for ultrasensitive detection of soluble PD-L1 in breast cancer based on decorated covalent organic frameworks and carbon nanotubes |
| 1685 | A. Eugene DePrince | NONE_EXPLICIT | none | Reduced-density-matrix-based ab initio cavity quantum electrodynamics |
| 1689 | Fengling Song | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | A Selenium‐Substituted Heptamethine Cyanine Photosensitizer for Near‐Infrared Photodynamic Therapy |
| 1696 | Wen-hong Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photoactivatable fluorophores and techniques for biological imaging applications |
| 1710 | Dan Lehnherr | Tomislav Rovis | none | Photons or Electrons? A Critical Comparison of Electrochemistry and Photoredox Catalysis for Organic Synthesis |
| 1713 | Chenjian Lin | Ryan M. Young, Michael R. Wasielewski | none | Accelerating symmetry-breaking charge separation in a perylenediimide trimer through a vibronically coherent dimer intermediate |
| 1713 | Taeyeon Kim | Ryan M. Young, Michael R. Wasielewski | none | Accelerating symmetry-breaking charge separation in a perylenediimide trimer through a vibronically coherent dimer intermediate |
| 1714 | David Casanova | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The role of CT excitations in PDI aggregates |
| 1718 | Marco Garavelli | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Multiple Electronic and Structural Factors Control Cyclobutane Pyrimidine Dimer and 6–4 Thymine–Thymine Photodimerization in a DNA Duplex |
| 1721 | Markus Sauer | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | How to switch a fluorophore: from undesired blinking to controlled photoswitching |
| 1722 | Peter Gilch | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The photoformation of a phthalide: a ketene intermediate traced by FSRS |
| 1729 | Hwan Myung Kim | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | An azo dye for photodynamic therapy that is activated selectively by two-photon excitation |
| 1737 | Zhen Huang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Synthesis of Pyrimidine Modified Seleno‐DNA as a Novel Approach to Antisense Candidate |
| 1742 | James Shee | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | In silico prediction of annihilators for triplet-triplet annihilation upconversion via auxiliary-field quantum Monte Carlo |
| 1751 | Masahiro Irie | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Carboxylated Photoswitchable Diarylethenes for Biolabeling and Super-Resolution RESOLFT Microscopy |
| 1751 | Stefan W. Hell | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Carboxylated Photoswitchable Diarylethenes for Biolabeling and Super-Resolution RESOLFT Microscopy |
| 1751 | Vladimir N. Belov | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Carboxylated Photoswitchable Diarylethenes for Biolabeling and Super-Resolution RESOLFT Microscopy |
| 1756 | Cheng Chen | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Characterization of Fluorescent Proteins Using Tunable Femtosecond Stimulated Raman Spectroscopy |
| 1756 | Chong Fang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Characterization of Fluorescent Proteins Using Tunable Femtosecond Stimulated Raman Spectroscopy |
| 1756 | Jacob M. Kirsh | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Characterization of Fluorescent Proteins Using Tunable Femtosecond Stimulated Raman Spectroscopy |
| 1756 | Mikhail S. Baranov | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Characterization of Fluorescent Proteins Using Tunable Femtosecond Stimulated Raman Spectroscopy |
| 1756 | Steven G. Boxer | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Structural Characterization of Fluorescent Proteins Using Tunable Femtosecond Stimulated Raman Spectroscopy |
| 1769 | Chong Fang | NONE_EXPLICIT | none | Photoswitchable Fluorescent Proteins: Mechanisms on Ultrafast Timescales |
| 1769 | Longteng Tang | NONE_EXPLICIT | none | Photoswitchable Fluorescent Proteins: Mechanisms on Ultrafast Timescales |
| 1774 | He Tian | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Endeavor of Diarylethenes: New Structures, High Performance, and Bright Future |
| 1780 | Frank Neese | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Electronic structure analysis of electrochemical CO <sub>2</sub> reduction by iron-porphyrins reveals basic requirements for design of catalysts bearing non-innocent ligands |
| 1780 | Shengfa Ye | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Electronic structure analysis of electrochemical CO <sub>2</sub> reduction by iron-porphyrins reveals basic requirements for design of catalysts bearing non-innocent ligands |
| 1789 | Juan Arago | NONE_EXPLICIT | none | Excitonic couplings between molecular crystal pairs by a multistate approximation |
| 1790 | Guoqing Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Versatile Room‐Temperature‐Phosphorescent Materials Prepared from N‐Substituted Naphthalimides: Emission Enhancement and Chemical Conjugation |
| 1790 | Xuepeng Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Versatile Room‐Temperature‐Phosphorescent Materials Prepared from N‐Substituted Naphthalimides: Emission Enhancement and Chemical Conjugation |
| 1796 | Max Marcus | NONE_EXPLICIT | none | Triplet-triplet decoherence in singlet fission |
| 1796 | William Barford | NONE_EXPLICIT | none | Triplet-triplet decoherence in singlet fission |
| 1800 | Ulrike Endesfelder | NONE_EXPLICIT | none | From single molecules to life: microscopy at the nanoscale |
| 1806 | Luis M. Campos | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | A design strategy for intramolecular singlet fission mediated by charge-transfer states in donor-acceptor organic materials |
| 1806 | Matthew Y. Sfeir | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | A design strategy for intramolecular singlet fission mediated by charge-transfer states in donor-acceptor organic materials |
| 1808 | Han Xiao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Single-atom replacement as a general approach towards visible-light/near-infrared heavy-atom-free photosensitizers for photodynamic therapy |
| 1810 | Xiaowei Zhuang | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE, ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | High-throughput, image-based screening of pooled genetic-variant libraries |
| 1814 | Mauro Gemmi | NONE_EXPLICIT | none | True molecular conformation and structure determination by three-dimensional electron diffraction of PAH by-products potentially useful for electronic applications |
| 1822 | Francesco Paesani | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Connecting the dots for fundamental understanding of structure-photophysics-property relationships of COFs, MOFs, and perovskites using a Multiparticle Holstein Formalism |
| 1825 | Bohdan Skalski | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Highly Efficient Fluorescent Interstrand Photo‐crosslinking of DNA Duplexes Labeled with 5‐Fluoro‐4‐thio‐2′‐ <i>O</i> ‐methyluridine |
| 1826 | J. Piette | M. Collet | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Photoreaction of new psoralen analogs with DNA: Sequence and mutation specificity in the Escherichia coli lacZ gene |
| 1829 | A. P. Savitsky | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | First biphotochromic fluorescent protein moxSAASoti stabilized for oxidizing environment |
| 1830 | Gregor Witte | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Regioselective Fluorination of Acenes: Tailoring of Molecular Electronic Levels and Solid-State Properties |
| 1830 | Ulrich Koert | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Regioselective Fluorination of Acenes: Tailoring of Molecular Electronic Levels and Solid-State Properties |
| 1833 | Zhaohui Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, FRONT_MATTER_DOI_CONFLICT | Metal–organic frameworks (MOFs) for photocatalytic CO <sub>2</sub> reduction |
| 1845 | Yoonkyung Kim | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | High-Contrast Reversible Fluorescence Photoswitching of Dye-Crosslinked Dendritic Nanoclusters in Living Vertebrates |
| 1853 | Lei Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Indications of 5′ to 3′ Interbase Electron Transfer as the First Step of Pyrimidine Dimer Formation Probed by a Dinucleotide Analog |
| 1863 | Oliver Weingart | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Photophysics of Dibenzo[a,j]phenazine |
| 1863 | Peter Gilch | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Photophysics of Dibenzo[a,j]phenazine |
| 1863 | Youhei Takeda | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Photophysics of Dibenzo[a,j]phenazine |
| 1864 | Giulio Cerullo | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet Fission in Dideuterated Tetracene and Pentacene |
| 1867 | Modesto Orozco | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The DNA-forming properties of 6-selenoguanine |
| 1868 | Yuanqin Xia | NONE_EXPLICIT | none | Research Progress on Singlet Fission in Acenes and Their Derivatives |
| 1873 | Maurizio Persico | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Diabatization by Localization in the Framework of Configuration Interaction Based on Floating Occupation Molecular Orbitals (FOMO−CI) |
| 1878 | Akiharu Satake | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photocatalytic CO <sub>2</sub> Reductions Catalyzed by <i>meso</i> ‐(1,10‐Phenanthrolin‐2‐yl)‐Porphyrins Having a Rhenium(I) Tricarbonyl Complex |
| 1878 | Yusuke Kuramochi | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photocatalytic CO <sub>2</sub> Reductions Catalyzed by <i>meso</i> ‐(1,10‐Phenanthrolin‐2‐yl)‐Porphyrins Having a Rhenium(I) Tricarbonyl Complex |
| 1880 | Ashok Maliakal | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photostability of pentacene and 6,13-disubstituted pentacene derivatives: a theoretical and experimental mechanistic study |
| 1883 | Alparslan Atahan | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Photophysical Properties of Triisopropylsilyl-ethynylpentacene-A Molecule with an Unusually Large Singlet-Triplet Energy Gap-In Solution and Solid Phases |
| 1883 | Anthony Harriman | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Photophysical Properties of Triisopropylsilyl-ethynylpentacene-A Molecule with an Unusually Large Singlet-Triplet Energy Gap-In Solution and Solid Phases |
| 1883 | Carlos Serpa | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Photophysical Properties of Triisopropylsilyl-ethynylpentacene-A Molecule with an Unusually Large Singlet-Triplet Energy Gap-In Solution and Solid Phases |
| 1883 | Fabio A. Schaberle | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | The Photophysical Properties of Triisopropylsilyl-ethynylpentacene-A Molecule with an Unusually Large Singlet-Triplet Energy Gap-In Solution and Solid Phases |
| 1886 | Giovanni Granucci | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Decoding the Molecular Basis for the Population Mechanism of the Triplet Phototoxic Precursors in UVA Light‐Activated Pyrimidine Anticancer Drugs |
| 1886 | Maurizio Persico | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Decoding the Molecular Basis for the Population Mechanism of the Triplet Phototoxic Precursors in UVA Light‐Activated Pyrimidine Anticancer Drugs |
| 1891 | Chong Fang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Switching between Ultrafast Pathways Enables a Green-Red Emission Ratiometric Fluorescent-Protein-Based Ca2+ Biosensor |
| 1891 | Liangdong Zhu | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Switching between Ultrafast Pathways Enables a Green-Red Emission Ratiometric Fluorescent-Protein-Based Ca2+ Biosensor |
| 1891 | Longteng Tang | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Switching between Ultrafast Pathways Enables a Green-Red Emission Ratiometric Fluorescent-Protein-Based Ca2+ Biosensor |
| 1891 | Nikita D. Rozanov | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Switching between Ultrafast Pathways Enables a Green-Red Emission Ratiometric Fluorescent-Protein-Based Ca2+ Biosensor |
| 1891 | Robert E. Campbell | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Switching between Ultrafast Pathways Enables a Green-Red Emission Ratiometric Fluorescent-Protein-Based Ca2+ Biosensor |
| 1895 | Igor Schapiro | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | QM/MM Benchmarking of Cyanobacteriochrome Slr1393g3 Absorption Spectra |
| 1897 | Gustavo Fuertes | NONE_EXPLICIT | none | Sub-Millisecond Photoinduced Dynamics of Free and EL222-Bound FMN by Stimulated Raman and Visible Absorption Spectroscopies |
| 1898 | Enis Arik | Marie Louise Groot | none | Confinement in crystal lattice alters entire photocycle pathway of the Photoactive Yellow Protein |
| 1905 | Chong Fang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Targeting Ultrafast Spectroscopic Insights into Red Fluorescent Proteins |
| 1911 | Chong Fang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Mapping the Complete Photocycle that Powers a Large Stokes Shift Red Fluorescent Protein |
| 1911 | Quanjiang Ji | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Mapping the Complete Photocycle that Powers a Large Stokes Shift Red Fluorescent Protein |
| 1911 | Weimin Liu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Mapping the Complete Photocycle that Powers a Large Stokes Shift Red Fluorescent Protein |
| 1911 | Yifan Huang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Mapping the Complete Photocycle that Powers a Large Stokes Shift Red Fluorescent Protein |
| 1917 | Donald G. Truhlar | Ke R. Yang, Xuefei Xu | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Direct diabatization of electronic states by the fourfold-way: Including dynamical correlation by multi-configuration quasidegenerate perturbation theory with complete active space self-consistent-field diabatic molecular orbitals |
| 1927 | Tahsin J. Chow | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Heptacene: Synthesis and Its Hole-Transfer Property in Stable Thin Films |
| 1927 | Takaaki Miyazaki | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Heptacene: Synthesis and Its Hole-Transfer Property in Stable Thin Films |
| 1935 | Taku Hasobe | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Effect of Torsional Motion on Multiexciton Formation through Intramolecular Singlet Fission in Ferrocene-Bridged Pentacene Dimers |
| 1935 | Yasuhiro Kobori | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The Effect of Torsional Motion on Multiexciton Formation through Intramolecular Singlet Fission in Ferrocene-Bridged Pentacene Dimers |
| 1936 | Garry Rumbles | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Slow charge transfer from pentacene triplet states at the Marcus optimum |
| 1937 | Lin Ma | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Charge transfer dynamics in a singlet fission organic molecule and organometal perovskite bilayer structure |
| 1939 | Tomás Torres | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Förster Resonance Energy Transfer Sensitized Singlet Fission in BODIPY-Pentacene Dimer Conjugates |
| 1952 | Miguel A. Miranda | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Photophysical properties of 5-substituted 2-thiopyrimidines |
| 1969 | Nino Russo | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Photophysical properties prediction of selenium- and tellurium-substituted thymidine as potential UVA chemotherapeutic agents |
| 1973 | Carlos E. Crespo-Hernández | NONE_EXPLICIT | none | Detection of the thietane precursor in the UVA formation of the DNA 6-4 photoadduct |
| 1973 | Sean J. Hoehn | NONE_EXPLICIT | none | Detection of the thietane precursor in the UVA formation of the DNA 6-4 photoadduct |
| 1975 | Hwan Myung Kim | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Design and synthesis of efficient heavy-atom-free photosensitizers for photodynamic therapy of cancer |
| 1975 | Juyoung Yoon | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Design and synthesis of efficient heavy-atom-free photosensitizers for photodynamic therapy of cancer |
| 1977 | Giovanni Granucci | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Competing ultrafast intersystem crossing and internal conversion: a time resolved picture for the deactivation of 6-thioguanine |
| 1985 | Sally Helen Ibbotson | NONE_EXPLICIT | none | Adverse effects of topical photodynamic therapy |
| 2006 | Susanne Ullrich | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Internal conversion and intersystem crossing pathways in UV excited, isolated uracils and their implications in prebiotic chemistry |
| 2007 | Ru Bo Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, FRONT_MATTER_DOI_CONFLICT | A triplet mechanism for the formation of thymine–thymine (6-4) dimers in UV-irradiated DNA |
| 2009 | Han Zhang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, FRONT_MATTER_DOI_CONFLICT | Emerging combination strategies with phototherapy in cancer nanomedicine |
| 2010 | Ganglong Cui | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The excited-state decay mechanism of 2,4-dithiothymine in the gas phase, microsolvated surroundings, and aqueous solution |
| 2013 | Haibo Yu | NONE_EXPLICIT | none | The effect of DNA backbone on the triplet mechanism of UV-induced thymine-thymine (6–4) dimer formation |
| 2013 | Xingyong Wang | NONE_EXPLICIT | none | The effect of DNA backbone on the triplet mechanism of UV-induced thymine-thymine (6–4) dimer formation |
| 2037 | ZJ Han | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Promoting photocatalytic CO2 reduction with a molecular copper purpurin chromophore |
| 2039 | Duobin Chao | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | A Small Organic Molecular Catalyst with Efficient Electron Accumulation for Near-unity CO2 Photoreduction |
| 2043 | Maylis Orio | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Highly Efficient Light-Driven CO2 to CO Reduction by an Appropriately Decorated Iron Porphyrin Molecular Catalyst |
| 2044 | Shiro Hikichi | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Selective alkane hydroxylation and alkene epoxidation using H2O2 and Fe(ii) catalysts electrostatically attached to a fluorinated surface |
| 2044 | Takahiko Kojima | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Selective alkane hydroxylation and alkene epoxidation using H2O2 and Fe(ii) catalysts electrostatically attached to a fluorinated surface |
| 2045 | Ally Aukauloo | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Second Coordination Sphere Effect Shifts CO2 to CO Reduction by Iron Porphyrin from Fe0 to FeI |
| 2045 | Sk Amanullah | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Second Coordination Sphere Effect Shifts CO2 to CO Reduction by Iron Porphyrin from Fe0 to FeI |
| 2045 | Zakaria Halime | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Second Coordination Sphere Effect Shifts CO2 to CO Reduction by Iron Porphyrin from Fe0 to FeI |
| 2063 | Ingo Fischer | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | The mechanism of excimer formation: an experimental and theoretical study on the pyrene dimer |
| 2077 | Soumitra Satapathi | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Recent Progress in Advanced Organic Photovoltaics: Emerging Techniques and Materials |
| 2079 | Peng Zhang | Michael J. Therien | NO_REFERENCE_SECTION | Orientational Dependence of Cofacial Porphyrin-Quinone Electronic Interactions within the Strong Coupling Regime |
| 2080 | Heyuan Liu | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Linker dependent symmetry breaking charge separation in 9,10-bis(phenylethynyl)anthracene dimers |
| 2080 | Xiyou Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Linker dependent symmetry breaking charge separation in 9,10-bis(phenylethynyl)anthracene dimers |
| 2086 | Siva Umapathy | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Unraveling structural dynamics in isoenergetic excited S1 and multi-excitonic 1(TT) states of 9,10-bis(phenylethynyl)anthracene (BPEA) in solution via ultrafast Raman loss spectroscopy Electronic supplementary information (ESI) available: Summary of the concentration-dependent kinetics of TA of BPEA, and the molecular structure of BPEA along with its numbering on each atom. See DOI: 10.1039/c8cp06658b |
| 2102 | David Casanova | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Theory of Exciton Dynamics in Thermally Activated Delayed Fluorescence |
| 2105 | Kenji Okada | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Monte Carlo Wavefunction Approach to Singlet Fission Dynamics of Molecular Aggregates |
| 2105 | Ryohei Kishi | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Monte Carlo Wavefunction Approach to Singlet Fission Dynamics of Molecular Aggregates |
| 2105 | Takanori Nagami | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Monte Carlo Wavefunction Approach to Singlet Fission Dynamics of Molecular Aggregates |
| 2105 | Takayoshi Tonami | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Monte Carlo Wavefunction Approach to Singlet Fission Dynamics of Molecular Aggregates |
| 2105 | Yasutaka Kitagawa | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Monte Carlo Wavefunction Approach to Singlet Fission Dynamics of Molecular Aggregates |
| 2107 | Jean-Luc Bredas | NONE_EXPLICIT | none | Charge-Transfer States in Organic Solar Cells: Understanding the Impact of Polarization, Delocalization, and Disorder |
| 2107 | Veaceslav Coropceanu | NONE_EXPLICIT | none | Charge-Transfer States in Organic Solar Cells: Understanding the Impact of Polarization, Delocalization, and Disorder |
| 2115 | Gregory D. Scholes | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Striking the right balance of intermolecular coupling for high-efficiency singlet fission |
| 2115 | John E. Anthony | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Striking the right balance of intermolecular coupling for high-efficiency singlet fission |
| 2122 | Klaus Brettel | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | [Ru(bpy)3]2+ as a reference in transient absorption spectroscopy: differential absorption coefficients for formation of the long-lived 3MLCT excited state |
| 2122 | Pavel Müller | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | [Ru(bpy)3]2+ as a reference in transient absorption spectroscopy: differential absorption coefficients for formation of the long-lived 3MLCT excited state |
| 2136 | G. Ulrich Nienhaus | NONE_EXPLICIT | none | Mechanistic Insights into Reversible Photoactivation in Proteins of the GFP Family |
| 2140 | Michael W. Davidson | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Sample preparation for single molecule localization microscopy |
| 2145 | Baotao Kang | NONE_EXPLICIT | none | Concerted Asynchronous Proton Transfer in H-Bonding Relay Model: An Implication of Green Fluorescent Protein |
| 2145 | Jin Yong Lee | NONE_EXPLICIT | none | Concerted Asynchronous Proton Transfer in H-Bonding Relay Model: An Implication of Green Fluorescent Protein |
| 2145 | S. Karthikeyan | NONE_EXPLICIT | none | Concerted Asynchronous Proton Transfer in H-Bonding Relay Model: An Implication of Green Fluorescent Protein |
| 2154 | Melike Lakadamyali | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL, FRONT_MATTER_DOI_CONFLICT | Super-Resolution Microscopy: Going Live and Going Fast |
| 2163 | Mark Prescott | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | X-Ray Crystal Structure and Properties of Phanta, a Weakly Fluorescent Photochromic GFP-Like Protein |
| 2173 | Thomas Friedrich | NONE_EXPLICIT | none | Disruption of Ankyrin B and Caveolin-1 Interaction Sites Alters Na+, K+-ATPase Membrane Diffusion |
| 2187 | Yujie Sun | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Nuclear peripheral chromatin-lamin B1 interaction is required for global integrity of chromatin architecture and dynamics in human cells |
| 2195 | Fernando D. Stefani | NONE_EXPLICIT | none | Multiphoton single-molecule localization by sequential excitation with light minima |
| 2207 | Malgorzata Biczysko | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Solvent effects on electron-driven proton-transfer processes: adenine–thymine base pairs |
| 2233 | Changqing Ye | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Multi-wavelength excited triplet-triplet upconversion microcrystals based on hot-band excitation for optical information encryption |
| 2233 | Shuoran Chen | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Multi-wavelength excited triplet-triplet upconversion microcrystals based on hot-band excitation for optical information encryption |
| 2237 | Nobuhiro Yanai | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Oligo(ethylene glycol)/alkyl-modified Chromophore Assemblies for Photon Upconversion in Water |
| 2238 | Nobuhiro Yanai | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Leaping across the visible range: near-infrared-to-violet photon upconversion employing a silyl-substituted anthracene |
| 2241 | Nobuhiro Yanai | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet-to-Triplet Absorption for Near-Infrared-to-Visible Photon Upconversion |
| 2253 | David Casanova | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Engineering the Charge-Transfer State to Facilitate Spin-Orbit Charge Transfer Intersystem Crossing in Spirobis[anthracene]diones |
| 2253 | Youjun Yang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Engineering the Charge-Transfer State to Facilitate Spin-Orbit Charge Transfer Intersystem Crossing in Spirobis[anthracene]diones |
| 2253 | Zuhai Lei | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Engineering the Charge-Transfer State to Facilitate Spin-Orbit Charge Transfer Intersystem Crossing in Spirobis[anthracene]diones |
| 2260 | Noa Marom | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Finding predictive models for singlet fission by machine learning |
| 2266 | David Casanova | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Near-Unity Triplet Generation Promoted via Spiro-Conjugation |
| 2266 | Youjun Yang | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Near-Unity Triplet Generation Promoted via Spiro-Conjugation |
| 2272 | Elise Y. Li | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Quest for singlet fission of organic sulfur-containing systems in the higher lying singlet excited state: application prospects of anti-Kasha's rule |
| 2277 | Mojtaba Alipour | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Singlet fission relevant energetics from optimally tuned range-separated hybrids |
| 2278 | Frank Schreiber | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Strong light-matter coupling in pentacene thin films on plasmonic arrays |
| 2278 | Monika Fleischer | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Strong light-matter coupling in pentacene thin films on plasmonic arrays |
| 2284 | Taku Hasobe | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Thermodynamic Control of Intramolecular Singlet Fission and Exciton Transport in Linear Tetracene Oligomers |
| 2284 | Yasuhiro Kobori | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Thermodynamic Control of Intramolecular Singlet Fission and Exciton Transport in Linear Tetracene Oligomers |
| 2286 | Benedetta Carlotti | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Unveiling the double triplet nature of the 2Ag state in conjugated stilbenoid compounds to achieve efficient singlet fission |
| 2336 | Bruno Robert | NONE_EXPLICIT | none | Site, trigger, quenching mechanism and recovery of non-photochemical quenching in cyanobacteria: recent updates |
| 2336 | Datta Madamwar | NONE_EXPLICIT | none | Site, trigger, quenching mechanism and recovery of non-photochemical quenching in cyanobacteria: recent updates |
| 2336 | Ravi R. Sonani | NONE_EXPLICIT | none | Site, trigger, quenching mechanism and recovery of non-photochemical quenching in cyanobacteria: recent updates |
| 2336 | Richard Cogdell | NONE_EXPLICIT | none | Site, trigger, quenching mechanism and recovery of non-photochemical quenching in cyanobacteria: recent updates |
| 2355 | Alexander Gerlach | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2355 | Frank Schreiber | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2355 | Gabriele D’Avino | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2355 | Hiroyuki Tamura | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2355 | Ingo Salzmann | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2355 | Valentina Belova | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2355 | Vincent O. Kim | David Beljonne | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet exciton fission via an intermolecular charge transfer state in coevaporated pentacene-perfluoropentacene thin films |
| 2366 | Hirohiko Houjou | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Coarse-grained lattice dynamics calculations combined with independent stiffness approximation: a comparative study on polymorphic molecular crystals |
| 2367 | Fabrizio Santoro | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Comparison of vertical and adiabatic harmonic approaches for the calculation of the vibrational structure of electronic spectra |
| 2382 | Patrick Bultinck | NONE_EXPLICIT | LOW_SOURCE_AUTHOR_HEADER_COVERAGE | Performance of Shannon-entropy compacted N-electron wave functions for configuration interaction methods |
| 2400 | Christian Schilling | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | What can quantum information theory offer to quantum chemistry? |
| 2411 | Joseph Ivanic | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | A MCSCF method for ground and excited states based on full optimizations of successive Jacobi rotations |
| 2421 | Hyotcherl Ihee | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Singlet fission dynamics modulated by molecular configuration in covalently linked pyrene dimers, Anti- and Syn-1,2-di(pyrenyl)benzene |
| 2425 | Michael R. Wasielewski | NONE_EXPLICIT | none | Enabling singlet fission by controlling intramolecular charge transfer in π-stacked covalent terrylenediimide dimers |
| 2427 | Josef Michl | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Guidance for Mutual Disposition of Chromophores for Singlet Fission |
| 2434 | Hyungjun Kim | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Coupled double triplet state in singlet fission |
| 2470 | Neill Lambert | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | QuTiP-BoFiN: A bosonic and fermionic numerical hierarchical-equations-of-motion library with applications in light-harvesting, quantum control, and single-molecule electronics |
| 2473 | David Picconi | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Implementation of quasiclassical mapping approaches for nonadiabatic molecular dynamics in the PySurf package |
| 2473 | Shirin Faraji | NONE_EXPLICIT | AUTHOR_MARKER_WITHOUT_ROLE_SIGNAL, CONTACT_WITHOUT_ROLE_SIGNAL | Implementation of quasiclassical mapping approaches for nonadiabatic molecular dynamics in the PySurf package |
| 2488 | M. Soriano | NONE_EXPLICIT | ROLE_EMAIL_AUTHOR_COUNT_MISMATCH | Theory of projections with nonorthogonal basis sets: Partitioning techniques and effective Hamiltonians |

## Review issues and root-cause evidence

| Issue | Count | Interpretation |
|---|---:|---|
| REFERENCE_SECTION_NOT_CONFIRMED | 1250 | Tail layout/heading or extraction did not establish a reliable bibliography section. |
| CONTACT_ONLY_NO_EXPLICIT_ROLE | 666 | Email/contact text was present without an explicit corresponding-author role. |
| AUTHOR_MARKER_WITHOUT_RESOLVED_ROLE | 255 | Author marker was visible but not enough by itself to establish a role under the conservative policy. |
| PARTIAL_SOURCE_AUTHOR_HEADER | 98 | Some source authors were not reliably visible in extracted front matter. |
| ROLE_SIGNAL_NOT_MAPPED_TO_SOURCE_AUTHOR | 82 | Role phrase present, but no unique source-mention mapping was safe. |
| SOURCE_AUTHORS_NOT_VISIBLE_IN_HEADER | 56 | Visible/extracted author header did not contain enough source-author evidence. |
| PRIMARY_SELECTION_OR_TITLE_MISMATCH | 23 | Selected PDF title/front matter did not match cleanly or looked supplementary. |
| IMAGE_ONLY_OR_EMPTY_FRONT_MATTER | 16 | OCR-needed or empty text layer; no speculative role truth recorded. |

## User-reported browser findings (2026-08-17)

The following findings were reported during browser verification after the audit overlay was made visible. They are recorded as defects and observations, not as repaired production behavior.

### 1. Audit result is not the Paperazzi record

- The browser overlay is intentionally read-only. `PDF audit ground truth` is an external audit conclusion and is not written into the paper's `CORRESPONDING` roles or the author identity links.
- Consequently, a paper can show confirmed PDF correspondence in the overlay while the normal paper view still shows no corresponding authors.
- The labels `EXPLICIT`, `NONE_EXPLICIT`, `ground truth`, and `machine prediction` were not sufficiently understandable in the UI. They need plain-language explanations such as “PDF核对结果：已确认通讯作者” and “当前数据库记录：尚未写入通讯作者”。

### 2. Paperazzi ID 2360: confirmed PDF correspondence but missing identity links

Paper `2360`, *Dynamics of Singlet Fission in the TIPS-Pn Cluster: Endothermic or Exothermic?*, has PDF author markers for `Xianfeng Qiao` and `Dongge Ma`. The local-AI review recorded both names as explicit correspondence ground truth. However, the Paperazzi record still reports no corresponding authors, and both paper-author mentions have `author_id = null`, `identity_status = UNRESOLVED`, and `roles = [ORDINARY]`.

Both canonical author profiles already exist and are linked on paper `1557`; therefore this is an identity-membership propagation/linking defect in addition to the read-only audit-overlay limitation. Because the paper-author mentions have no `author_id`, the browser correctly cannot render profile links for those two names.

### 3. Paperazzi ID 1156: three marked authors, only two parser predictions

Paper `1156`, *Torsional Motion Effect on the Quintet Multiexciton Formation through Intramolecular Singlet Fission in Ferrocene-Bridged Pentacene Dimers*, shows `Nikolai V. Tkachenko*`, `Yasuhiro Kobori*`, and `Taku Hasobe*`, with three corresponding contact blocks. The deterministic parser predicted only `Yasuhiro Kobori` and `Taku Hasobe`; it missed `Nikolai V. Tkachenko`. The formal Paperazzi record currently has no corresponding-author role for any of the three.

The audit row was incorrectly classified as `NONE_EXPLICIT` because the layout uses publisher star/email convention rather than a literal “corresponding author” sentence. The source spelling `Nikolai V Tkachenko` also differs from the PDF spelling `Nikolai V. Tkachenko`, exposing a punctuation/author-mapping weakness.

### 4. Paperazzi ID 886: three contact authors, zero correspondence predictions

Paper `886`, *Accessing sulfonamides via formal SO2 insertion into C–N bonds*, contains three contact emails for `Christopher B. Kelly`, `Christopher A. Reiher`, and `Mark D. Levin`. The current Paperazzi record has all seven author identities resolved, but `corresponding_authors` is empty. The deterministic parser predicted zero authors and the local-AI row was classified as `NONE_EXPLICIT` with `CONTACT_ONLY_NO_EXPLICIT_ROLE`.

This is a complete `0/3` correspondence miss, not an identity-link problem. The extracted text retained the contact block but lost or failed to interpret the author-side icons/markers. The Zotero item is also recorded as a ChemRxiv preprint while the selected PDF front matter carries the published Nature Chemistry DOI, so document/version identity must be reviewed before promotion.

### 5. Full-library audit methodology limitation

The batch did read and review all 2,060 PDFs in the queue, but the review was primarily text-extraction-based and did not provide reliable page-image inspection of small author-side icons, stars, envelopes, or publisher-specific correspondence layouts. The audit therefore detected warning signals in cases such as `886` without converting them into correct correspondence truth. The final score already records the consequence: recall `0.2089`, with `1,030` false negatives, and the gate remains `FAIL / BLOCKED`. “Batch completed” must not be represented as “correspondence correctness validated.”

### 6. Identity Review merge queue disappearance bug (user reproduction)

Reported reproduction: when Identity Review contains three or more similar names, merging one selected name into another causes the remaining similar-name entries to disappear from the page. After a refresh they may reappear, but the remaining unmerged candidate is no longer shown as similar.

Expected behavior: one merge should modify only the selected pair; every other open candidate and its similarity relationship must remain visible. Current impact is high because the review queue can hide unresolved identity decisions and make it appear that no further review is required. This report records the behavior as `P1 / pending independent reproduction`; no data deletion has been proven from the browser symptom alone.

## Required deliverables

- `summary.json`, `all_papers.jsonl`, `ai_review_queue.jsonl`, `ai_reviews.jsonl`, `score.json`, and this report are stored together in this run directory.
- `ai_reviews.jsonl` is an external benchmark only; it was not imported into Paperazzi.
- No production fixes were applied during the audit.

## Final disposition

**FAIL / BLOCKED**. The audit is complete and reproducible, but correspondence population must not be promoted from this result. The next repair cycle should use the FP/FN tables and the representative PDF IDs above to implement publisher/layout-specific evidence mapping, then rerun the full scorer and browser validation.
