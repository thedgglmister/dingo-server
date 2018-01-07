CREATE TABLE users (username TEXT, password TEXT);
CREATE TABLE dogs (breed TEXT, filename TEXT);
CREATE TABLE cards (username TEXT, slot INTEGER, breed TEXT);
INSERT INTO dogs (breed, filename)
VALUES ('Golden Retriever', 'golden_retriever.jpg'),
       ('English Setter', 'english_setter.jpg'),
       ('Beagle', 'beagle.jpg'),
       ('Weimaraner', 'weimaraner.jpg');

