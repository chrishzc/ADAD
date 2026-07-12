# -*- coding: utf-8 -*-
import sys
import json
from adad_core import ADADCore

def main():
    core = ADADCore()
    result = core.check_domain_boundary()

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["passed"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
