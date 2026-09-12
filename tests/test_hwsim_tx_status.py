from pathlib import Path
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/hwsim/0010-mac80211_hwsim-complete-aggregation-feedback.patch"


def feedback_source():
    source = os.environ.get("HWSIM_TEST_SOURCE")
    if source:
        content = Path(source).read_text()
    else:
        content = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                            if line.startswith("+") and not line.startswith("+++"))
    start = content.index("static void mac80211_hwsim_complete_ampdu_status(")
    end = content.index("\n}", start) + 2
    return content[start:end]


@pytest.mark.parametrize("feedback", [False, True])
def test_singleton_feedback_accounts_for_ack_and_failure(tmp_path, feedback):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler required for actual hwsim feedback helper")
    source = tmp_path / "feedback.c"
    source.write_text("""#include <stdbool.h>
#include <stdint.h>
#define IEEE80211_TX_CTL_NO_ACK (1U << 2)
#define IEEE80211_TX_CTL_AMPDU (1U << 6)
#define IEEE80211_TX_STAT_ACK (1U << 9)
#define IEEE80211_TX_STAT_AMPDU (1U << 10)
struct ieee80211_tx_info {
    uint32_t flags;
    struct { uint8_t ampdu_len; uint8_t ampdu_ack_len; } status;
};
""" + feedback_source() + """
int main(void)
{
    for (unsigned int requested = 0; requested < 2; requested++) {
        for (unsigned int acknowledged = 0; acknowledged < 2; acknowledged++) {
            struct ieee80211_tx_info info = {
                .flags = requested * IEEE80211_TX_CTL_AMPDU | acknowledged * IEEE80211_TX_STAT_ACK,
            };
            uint32_t original_flags = info.flags;
#ifdef FEEDBACK
            mac80211_hwsim_complete_ampdu_status(&info);
#endif
            if ((info.flags & ~IEEE80211_TX_STAT_AMPDU) != original_flags)
                return 1;
            if (requested && (!(info.flags & IEEE80211_TX_STAT_AMPDU) ||
                info.status.ampdu_len != 1 || info.status.ampdu_ack_len != acknowledged))
                return 2;
            if (!requested && (info.status.ampdu_len || info.status.ampdu_ack_len ||
                (info.flags & IEEE80211_TX_STAT_AMPDU)))
                return 3;
        }
    }
    struct ieee80211_tx_info no_ack = {.flags = IEEE80211_TX_CTL_AMPDU | IEEE80211_TX_CTL_NO_ACK};
    mac80211_hwsim_complete_ampdu_status(&no_ack);
    if (no_ack.status.ampdu_ack_len || (no_ack.flags & IEEE80211_TX_STAT_ACK))
        return 4;
    return 0;
}
""")
    binary = tmp_path / "feedback"
    subprocess.run([compiler, "-Wall", "-Werror", *(["-DFEEDBACK"] if feedback else []),
                    str(source), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], check=False)
    assert result.returncode == (0 if feedback else 2)


def test_both_tx_completion_paths_report_feedback():
    content = Path(os.environ["HWSIM_TEST_SOURCE"]).read_text() if os.environ.get("HWSIM_TEST_SOURCE") else PATCH.read_text()
    assert content.count("mac80211_hwsim_complete_ampdu_status(txi);") == 2
    builder = (ROOT / "scripts/build-hwsim.sh").read_text()
    assert 'patches/hwsim/[0-9][0-9][0-9][0-9]-*.patch' in builder
