// Local binary I/O harness for the existing author GPL ViterbiPath; no decoder edits.
#include "viterbi.h"
#include <cstdint>
#include <fstream>
#include <cmath>
#include <stdexcept>
#include <iostream>
int main(int argc,char**argv){
 try{
  if(argc!=3)throw std::runtime_error("Expected input/output binary paths");
  std::ifstream in(argv[1],std::ios::binary);std::uint64_t frames=0,states=0;
  in.read(reinterpret_cast<char*>(&frames),sizeof(frames));in.read(reinterpret_cast<char*>(&states),sizeof(states));
  if(!in||frames==0||frames>20000||states<2||states>1000)throw std::runtime_error("Invalid dimensions");
  std::vector<std::vector<double>> obs(frames,std::vector<double>(states));
  for(auto& row:obs){
   in.read(reinterpret_cast<char*>(row.data()),sizeof(double)*states);
   double sum=0;for(double value:row){if(!std::isfinite(value)||value<0)throw std::runtime_error("Invalid emission");sum+=value;}
   if(sum<=0||row.back()<=0)throw std::runtime_error("Missing retained N support");
  }
  if(!in||in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Wrong input length");
  double selftransprob=0.99;
  std::vector<double> init(states,0);init[states-1]=1;
  std::vector<std::vector<double>> trans;
  for(std::uint64_t i=0;i<states;++i){std::vector<double> row(states,(1-selftransprob)/(states-1));row[i]=selftransprob;trans.push_back(row);}
  std::vector<double> delta(frames*states),scale;
  auto path=ViterbiPath(init,trans,obs,delta.data(),&scale);
  std::ofstream out(argv[2],std::ios::binary);
  for(auto state:path){std::int32_t value=state;out.write(reinterpret_cast<char*>(&value),sizeof(value));}
  if(!out)throw std::runtime_error("Output write failed");
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
