# Test audio

None of this is in the repository. `api/scripts/eval_natural_audio.py` fetches it into
`storage/natural/`, which is gitignored.

| Set | Language | What it is | Licence | Used by default |
| :-- | :-- | :-- | :-- | :-- |
| [AMI](https://huggingface.co/datasets/edinburghcstr/ami) | English | Real meetings, human transcripts | CC-BY-4.0 | Yes |
| [Unified Urdu Speech](https://huggingface.co/datasets/abidanoaman/unified-urdu-speech-asr) (Common Voice part) | Urdu | Volunteers reading sentences aloud | CC-BY-4.0 as stated by the collection | Yes |
| [Nexdata sample](https://huggingface.co/datasets/Nexdata-AI/352-Hours-Urdu-Full-Duplex-Spontaneous-Dialogue-Smartphone-speech-Data-Sample) | Urdu | Spontaneous dialogue | None stated | Only with `--include-unverified` |
| [CSALT voice](https://huggingface.co/datasets/urdu-asr/csalt-voice) | Urdu | Natural speech | None stated | Only with `--include-unverified` |
| `storage/samples/real/sales_en_1.wav` | English | Sales conversation | Unknown source | Only with `--include-unverified` |

The default sets have clear terms but are not sales calls, and the Urdu is read aloud
rather than spontaneous. The unverified sets are closer to real calls. Use them for
private testing only: do not redistribute them, and do not publish results from them
until the terms are confirmed with whoever owns them.

There is still no open dataset of spoken Urdu-English code-switching. The fix is your
own recordings, with consent from everyone on the call.
