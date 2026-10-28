STEPS to capture:

Connect MDO34 to computer via point-to-point ethernet.
Set scope to same subnet as computer via Utility -> I/O => Instrument IP and subnet mask. (eg. scope mask = laptop mask, IP offset by 1)
Gateway and DNS to 0.0.0.0
Network address = Manual

Use ScopeCapture.py for capture. Inspect with --help
CRUCIAL: Sample rate not directly controlled - instead, set timebase (time/div), and record length (points per window - ie. 10 times timebase). BUT - Sps chooses from a small list of options - not exact calculation. 

Captures are stored in timestamped folders as .npz files (small file size).

Can be processed into csv and images via ProcessCapture.py. Inspect with --help.
Can point at file or folder (which will process everything in folder). 
Image outputs not tested much - trust the csv data.