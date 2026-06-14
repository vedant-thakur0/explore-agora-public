# Data Licensing

## Source dataset: AGORA (Zenodo)

The derived datasets in `knowledge_graph/graph_data/` (and the filtered corpus CSVs in `data/`) are filtered subsets of the AGORA corpus published on Zenodo:

> AGORA: AI Policy Document Corpus. Zenodo. https://zenodo.org/records/15692257

Please consult the Zenodo record for the canonical source license and citation requirements. Any redistribution of derived data in this repository is subject to the terms of the source dataset.

## Derived data in this repository

The corpus CSVs under `data/` (`documents.csv`, `segments.csv`) and the sponsor/cosponsor CSVs under `knowledge_graph/graph_data/` are produced by filtering and joining the AGORA corpus to the Congress-only slice used in this toolkit. They are released for research and reproducibility under the same terms as the source AGORA dataset.

If you use these derived files, please cite **both** the source AGORA dataset and this repository.

## Code

Code in this repository is licensed under the [MIT License](LICENSE), separately from the data terms above.
