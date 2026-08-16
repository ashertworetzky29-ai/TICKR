#!/bin/bash
# Run TICKR website locally
cd "$(dirname "$0")/tickr_website"
echo "Starting TICKR website on http://localhost:10000"
echo "Quant Lab will use ../tickr_alpha_engine/quant_model.py"
python server.py
