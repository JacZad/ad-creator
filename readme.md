\# AD Creator



AD Creator to aplikacja do automatycznego tworzenia audiodeskrypcji do filmów. Wykorzystuje do tego model Gemini 2.5.



\## Sposób działania



1. Użytkownik wkleja link do filmu, na przykład na YouTube, Vimeo lub na chmurowym dysku.
2. Do pola tekstowego wpisuje kontekst, na przykład imiona osób, informacja o lokalizacji, opis sytuacji.
3. Aplikacja Tworzy tekst audiodeskrypcji na podstawie treści filmu i kontekstu. Uwzględnia znaczniki czasu.
4. Na podstawie tekstu audiodeskrypcji generowana jest mowa, również za pomocą AI od Google.
5. Po wykonaniu zadania audiodeskrypcję można odsłuchać.
6. Aplikacja miksuje film z audiodeskrypcją, ale tylko na życzenie użytkownika.



\## Stos technologiczny



1. Modele Gemini z kluczem API w zmiennych środowiskowych systemu.
2. Python
3. Streamlit



\## Zasady tworzenia audiodeskrypcji



1. Audiodeskrypcja powinna być umieszczana w miejscach, gdzie nie mowy, żeby jej nie zagłuszać.
2. Opisy są konkretne i krótkie.
3. Opisy powinny dotyczyć tylko tych informacji, których nie da się wywnioskować z wypowiedzi lub dźwięków.



