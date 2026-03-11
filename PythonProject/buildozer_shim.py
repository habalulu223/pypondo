import sys
import urllib.request as urllib_request


if not hasattr(urllib_request, "FancyURLopener"):
    class CompatFancyURLopener(object):
        version = "Python-urllib/3.14"

        def retrieve(self, url, filename=None, reporthook=None, data=None):
            return urllib_request.urlretrieve(
                url,
                filename=filename,
                reporthook=reporthook,
                data=data,
            )

    urllib_request.FancyURLopener = CompatFancyURLopener

# Forward arguments to buildozer exactly as provided.
sys.argv = ["buildozer", *sys.argv[1:]]
from buildozer.scripts.client import main as buildozer_main
buildozer_main()
